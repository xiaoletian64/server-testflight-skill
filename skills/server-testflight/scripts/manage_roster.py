#!/usr/bin/env python3
"""Edit the account-private roster; removed entries revoke managed-group access on sync."""
import argparse
import fcntl
import json
import os
from pathlib import Path


def edit(data, action, email=None, fields=None):
    result = {'testers': data, 'removed': []} if isinstance(data, list) else {'testers': list(data['testers']), 'removed': list(data.get('removed', []))}
    if action == 'list': return result
    email = email.strip().lower()
    if '@' not in email: raise ValueError('Invalid email')
    existing = next((x for x in result['testers'] if x['email'].lower() == email), None)
    if action == 'add':
        if existing: existing.update(fields or {})
        else: result['testers'].append({'email': email, **(fields or {})})
        result['removed'] = [x for x in result['removed'] if x.lower() != email]
    elif action == 'remove':
        result['testers'] = [x for x in result['testers'] if x['email'].lower() != email]
        if email not in result['removed']: result['removed'].append(email)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['list','add','remove']);p.add_argument('--roster',type=Path,required=True)
    p.add_argument('--email');p.add_argument('--first-name');p.add_argument('--last-name')
    p.add_argument('--allow-team-invitation',action='store_true');p.add_argument('--allow-add-marketing',action='store_true');p.add_argument('--allow-app-access',action='store_true')
    a=p.parse_args()
    if a.action!='list' and not a.email:p.error('--email is required')
    os.umask(0o077)
    with a.roster.with_suffix('.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        fields={}
        for key in ['first_name','last_name','allow_team_invitation','allow_add_marketing','allow_app_access']:
            value=getattr(a,key)
            if value:fields[key]=value
        data=edit(json.loads(a.roster.read_text()),a.action,a.email,fields)
        if a.action!='list':
            tmp=a.roster.with_suffix('.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2));tmp.replace(a.roster)
    print(json.dumps(data,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
