#!/usr/bin/env python3
"""Reconcile an explicitly authorized, server-private internal tester roster."""
import argparse
import json
from pathlib import Path
import subprocess
import urllib.error
import urllib.parse
import urllib.request

ELIGIBLE = {'ACCOUNT_HOLDER', 'ADMIN', 'APP_MANAGER', 'DEVELOPER', 'MARKETING'}


class Apple:
    def __init__(self, config):
        self.config = config
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({})) if config.get('direct_network') else urllib.request.build_opener()

    def api(self, method, path, body=None):
        # Token provider is a local credential adapter, never a remote URL.
        p = subprocess.run(self.config['token_command'], check=True, capture_output=True, text=True)
        token = p.stdout.strip()
        if not token or '\n' in token:
            raise ValueError('Invalid token provider result')
        req = urllib.request.Request('https://api.appstoreconnect.apple.com' + path,
            data=json.dumps(body).encode() if body is not None else None, method=method,
            headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
        try:
            with self.opener.open(req, timeout=60) as r:
                raw = r.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            # Apple bodies may echo contacts; keep them out of shared logs.
            raise RuntimeError('Apple roster request failed: HTTP ' + str(e.code)) from None

    def all(self, path):
        result = []
        while path:
            page = self.api('GET', path)
            result.extend(page['data'])
            url = page.get('links', {}).get('next')
            if url:
                parsed = urllib.parse.urlparse(url)
                if parsed.scheme != 'https' or parsed.netloc != 'api.appstoreconnect.apple.com':
                    raise ValueError('Unexpected pagination host')
                path = parsed.path + ('?' + parsed.query if parsed.query else '')
            else:
                path = None
        return result


def reconcile(api, config, roster, send_invites=False, removed=None):
    app = config['app_id']; group_id = config['group_id']
    app_record = api.api('GET', '/v1/apps/' + app)['data']
    if app_record['attributes']['bundleId'] != config['bundle_id']:
        raise ValueError('App bundle mismatch')
    group = api.api('GET', '/v1/betaGroups/' + group_id + '?include=app')['data']
    if not group['attributes'].get('isInternalGroup') or group['relationships']['app']['data']['id'] != app:
        raise ValueError('Group is not internal or belongs to another app')
    if not group['attributes'].get('hasAccessToAllBuilds'):
        raise ValueError('Configure automatic build access on the intended internal group first')
    users = {x['attributes']['username'].lower(): x for x in api.all('/v1/users?limit=200')}
    pending = {x['attributes']['email'].lower(): x for x in api.all('/v1/userInvitations?limit=200')}
    testers = {x['attributes']['email'].lower(): x for x in api.all('/v1/betaGroups/' + group_id + '/betaTesters?limit=200')}
    results = []
    for email in removed or []:
        email = email.strip().lower()
        if any(x['email'].strip().lower() == email for x in roster):
            raise ValueError('Email is both active and removed in roster')
        tester = testers.get(email)
        if tester:
            api.api('DELETE', '/v1/betaGroups/' + group_id + '/relationships/betaTesters', {
                'data': [{'type': 'betaTesters', 'id': tester['id']}]})
            del testers[email]
        results.append({'email': email, 'state': 'REMOVED', 'removed': True})
    # Never remove unrelated users, roles or testers. Authorization is per entry.
    for entry in roster:
        email = entry['email'].strip().lower()
        if not email or '@' not in email:
            raise ValueError('Invalid roster email')
        try:
            user = users.get(email)
            if not user:
                if email not in pending:
                    if not entry.get('allow_team_invitation'):
                        results.append({'email': email, 'state': 'TEAM_INVITATION_AUTHORIZATION_REQUIRED'}); continue
                    invitation = api.api('POST', '/v1/userInvitations', {'data': {
                        'type': 'userInvitations', 'attributes': {
                            'email': email, 'firstName': entry['first_name'], 'lastName': entry['last_name'],
                            'roles': ['MARKETING'], 'allAppsVisible': False, 'provisioningAllowed': False},
                        'relationships': {'visibleApps': {'data': [{'type': 'apps', 'id': app}]}}}})['data']
                    pending[email] = invitation
                results.append({'email': email, 'state': 'TEAM_INVITATION_PENDING'})
                continue
            attrs = user['attributes']; roles = attrs.get('roles', [])
            if not ELIGIBLE.intersection(roles):
                if not entry.get('allow_add_marketing'):
                    results.append({'email': email, 'state': 'ROLE_AUTHORIZATION_REQUIRED'}); continue
                api.api('PATCH', '/v1/users/' + user['id'], {'data': {'type': 'users', 'id': user['id'],
                    'attributes': {'roles': roles + ['MARKETING']}}})
                roles = roles + ['MARKETING']
            if not attrs.get('allAppsVisible'):
                visible = api.all('/v1/users/' + user['id'] + '/visibleApps?limit=200')
                if not any(x['id'] == app for x in visible):
                    if not entry.get('allow_app_access'):
                        results.append({'email': email, 'state': 'APP_ACCESS_AUTHORIZATION_REQUIRED'}); continue
                    api.api('PATCH', '/v1/users/' + user['id'], {'data': {'type': 'users', 'id': user['id'],
                        'relationships': {'visibleApps': {'data': [{'type': 'apps', 'id': x['id']} for x in visible] + [{'type': 'apps', 'id': app}]}}}})
            tester = testers.get(email)
            newly_added = tester is None
            if newly_added:
                tester = api.api('POST', '/v1/betaTesters', {'data': {'type': 'betaTesters',
                    'attributes': {'email': email}, 'relationships': {'betaGroups': {
                        'data': [{'type': 'betaGroups', 'id': group_id}]}}}})['data']
                testers[email] = tester
            # Adding a tester normally sends the initial invitation. Explicit resend
            # only applies to an already-present unaccepted tester, never per release.
            if send_invites and not newly_added and tester['attributes'].get('state') == 'INVITED':
                api.api('POST', '/v1/betaTesterInvitations', {'data': {'type': 'betaTesterInvitations',
                    'relationships': {'app': {'data': {'type': 'apps', 'id': app}},
                                      'betaTester': {'data': {'type': 'betaTesters', 'id': tester['id']}}}}})
            results.append({'email': email, 'state': tester['attributes'].get('state') or 'ADDED', 'roles': roles})
        except RuntimeError as error:
            results.append({'email': email, 'state': 'SYNC_FAILED', 'error': str(error)})
    # Read back membership rather than treating a successful POST as proof.
    verified = {x['attributes']['email'].lower(): x for x in api.all('/v1/betaGroups/' + group_id + '/betaTesters?limit=200')}
    for item in results:
        item['member'] = item['email'] in verified
        if item.get('removed') and item['member']:
            item['state'] = 'REMOVAL_FAILED'
        elif item['member']:
            item['state'] = verified[item['email']]['attributes'].get('state') or item['state']
    return results


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--resend-pending', action='store_true')
    p.add_argument('--show-emails', action='store_true', help='Private operator session only')
    args = p.parse_args()
    config = json.loads(args.config.read_text())
    data = json.loads(Path(config['roster_file']).read_text())
    roster = data if isinstance(data, list) else data['testers']
    removed = [] if isinstance(data, list) else data.get('removed', [])
    results = reconcile(Apple(config), config, roster, args.resend_pending, removed)
    if not args.show_emails:
        for i, item in enumerate(results, 1): item['email'] = 'roster-entry-' + str(i)
    print(json.dumps({'internalRoster': results}, ensure_ascii=False, indent=2))
    if any((not x.get('removed') and not x['member'] and x['state'] != 'TEAM_INVITATION_PENDING') or x['state'] == 'REMOVAL_FAILED' for x in results):
        raise SystemExit(2)


if __name__ == '__main__': main()
