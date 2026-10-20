#!/usr/bin/env python3
"""Linux coordinator for a cloud macOS build and server-side Apple API upload."""
import argparse
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import subprocess
import time
import zipfile


def command(argv, capture=False):
    result = subprocess.run(argv, check=True, text=True, stdout=subprocess.PIPE if capture else None)
    return result.stdout.strip() if capture else None


def gh(repo, path, method='GET', body=None):
    argv = ['gh', 'api', 'repos/' + repo + path, '--method', method]
    if body is not None:
        argv += ['--input', '-']
    p = subprocess.run(argv, input=json.dumps(body) if body is not None else None,
                       text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode:
        raise RuntimeError('GitHub API failed (details remain on server; no credentials logged)')
    return json.loads(p.stdout) if p.stdout.strip() else {}


def check_ipa(path, bundle, version, number, minimum):
    with zipfile.ZipFile(path) as z:
        files = [n for n in z.namelist() if re.fullmatch(r'Payload/[^/]+\.app/Info.plist', n)]
        if len(files) != 1:
            raise ValueError('Expected one top-level iOS app')
        info = plistlib.loads(z.read(files[0]))
    if (info.get('CFBundleIdentifier'), info.get('CFBundleShortVersionString'), str(info.get('CFBundleVersion'))) != (bundle, version, number):
        raise ValueError('Artifact identity mismatch')
    v = lambda s: tuple(int(x) for x in s.split('.'))
    if v(info.get('MinimumOSVersion', '0')) < v(minimum):
        raise ValueError('Artifact minimum iOS version below configured floor')


def save(path, value):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, indent=2))
    tmp.replace(path)


def adapters(config, key, values):
    argv = config[key]
    if not isinstance(argv, list) or not all(isinstance(x, str) for x in argv):
        raise ValueError('Adapter must be an argv array')
    return [x.format_map(values) for x in argv]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--version', required=True)
    p.add_argument('--build-number', required=True)
    p.add_argument('--check', action='store_true', help='Read-only dependency and configuration preflight')
    p.add_argument('--submit-review', action='store_true')
    p.add_argument('--enable-public-link', action='store_true')
    args = p.parse_args()
    if not re.fullmatch(r'\d+\.\d+\.\d+', args.version) or not re.fullmatch(r'[1-9]\d*', args.build_number):
        p.error('Use a numeric version and positive integer build number')
    c = json.loads(args.config.read_text())
    if c.get('direct_network', False):
        for key in list(os.environ):
            if key.lower() in ('http_proxy', 'https_proxy', 'all_proxy'):
                os.environ.pop(key)
    os.umask(0o077)
    repo = c['repository']
    # Refuse adapters with absent scripts early, before triggering a paid build.
    command(['gh', 'auth', 'status'], capture=True)
    for name in ('sign_command', 'upload_command', 'finish_command'):
        if not isinstance(c[name], list) or not c[name]:
            raise ValueError('Missing command adapter: ' + name)
    if args.check:
        gh(repo, '/actions/workflows/' + c['workflow'])
        print('Preflight passed; no build, upload or review was started.')
        return
    root = Path(c['state_directory'])
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = (root / 'release.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        work = root / (args.version + '-' + args.build_number)
        work.mkdir(mode=0o700, exist_ok=True)
        state_path = work / 'release.json'
        identity = {'repository': repo, 'bundle': c['bundle_id'], 'version': args.version, 'number': args.build_number}
        state = json.loads(state_path.read_text()) if state_path.exists() else dict(identity)
        if any(state.get(k) != v for k, v in identity.items()):
            raise ValueError('Resume identity mismatch')
        if 'head' not in state:
            state['head'] = gh(repo, '/commits/' + c.get('ref', 'main'))['sha']
            state['started'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            state['run_title'] = f"server-release-{args.version}-{args.build_number}"
            # Save before dispatch: a lost HTTP response must not create duplicate runs.
            state['dispatch_attempted'] = True
            save(state_path, state)
            gh(repo, '/actions/workflows/' + c['workflow'] + '/dispatches', 'POST', {
                'ref': c.get('ref', 'main'), 'inputs': {'build_name': args.version, 'build_number': args.build_number,
                                              'platform': 'ios', 'release_id': state['run_title']}})
        deadline = time.monotonic() + c.get('timeout_seconds', 10800)
        while 'run_id' not in state:
            runs = gh(repo, '/actions/workflows/' + c['workflow'] + '/runs?event=workflow_dispatch&per_page=100')['workflow_runs']
            matches = [r for r in runs if r['head_sha'] == state['head'] and r['display_title'] == state['run_title'] and r['created_at'] >= state['started'][:19] + 'Z']
            if len(matches) > 1:
                raise RuntimeError('Multiple matching runs; inspect before resuming')
            if matches:
                state['run_id'] = matches[0]['id']; save(state_path, state); break
            if time.monotonic() >= deadline:
                raise TimeoutError('No matching dispatch found; inspect workflow before resetting state')
            time.sleep(15)
        while True:
            run = gh(repo, '/actions/runs/' + str(state['run_id']))
            if run['head_sha'] != state['head']:
                raise ValueError('Workflow commit mismatch')
            if run['status'] == 'completed':
                if run['conclusion'] != 'success':
                    raise RuntimeError('Cloud build failed: ' + str(run['conclusion']))
                break
            if time.monotonic() >= deadline:
                raise TimeoutError('Cloud build timed out; same command resumes this run')
            time.sleep(30)
        unsigned = work / 'artifact' / c.get('artifact_file', 'ios-unsigned.ipa')
        if not unsigned.exists():
            command(['gh', 'run', 'download', str(state['run_id']), '--repo', repo, '--name',
                     c['artifact_name'].format(version=args.version, number=args.build_number), '--dir', str(unsigned.parent)])
        check_ipa(unsigned, c['bundle_id'], args.version, args.build_number, c.get('minimum_ios', '15.0'))
        values = {'unsigned': str(unsigned), 'signed': str(work / 'signed.ipa'), 'work': str(work),
                  'version': args.version, 'number': args.build_number}
        signed = Path(values['signed'])
        if 'signed_sha256' in state:
            if not signed.exists() or hashlib.sha256(signed.read_bytes()).hexdigest() != state['signed_sha256']:
                raise ValueError('Signed artifact differs from resume record')
        else:
            command(adapters(c, 'sign_command', values))
            check_ipa(signed, c['bundle_id'], args.version, args.build_number, c.get('minimum_ios', '15.0'))
            state['signed_sha256'] = hashlib.sha256(signed.read_bytes()).hexdigest()
            save(state_path, state)
        command(adapters(c, 'upload_command', values))
        finish = adapters(c, 'finish_command', values)
        if args.submit_review: finish.append('--submit-review')
        if args.enable_public_link: finish.append('--enable-public-link')
        command(finish)
        print('Server pipeline finished; use the reported Apple state to determine tester availability.')
    finally:
        lock.close()


if __name__ == '__main__':
    main()
