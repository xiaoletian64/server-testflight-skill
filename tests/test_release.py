import importlib.util
import json
from pathlib import Path
import plistlib
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

SCRIPT = Path(__file__).resolve().parents[1] / 'skills/server-testflight/scripts/release.py'
spec = importlib.util.spec_from_file_location('release', SCRIPT)
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def ipa(path, number='3', minimum='15.0'):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('Payload/App.app/Info.plist', plistlib.dumps({
            'CFBundleIdentifier': 'org.example.app', 'CFBundleShortVersionString': '1.0.0',
            'CFBundleVersion': number, 'MinimumOSVersion': minimum}))


class ReleaseTests(unittest.TestCase):
    def test_wrong_build_or_os_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'a.ipa'
            ipa(p, number='4')
            with self.assertRaises(ValueError): release.check_ipa(p, 'org.example.app', '1.0.0', '3', '15.0')
            ipa(p, minimum='13.0')
            with self.assertRaises(ValueError): release.check_ipa(p, 'org.example.app', '1.0.0', '3', '15.0')

    def test_resume_never_dispatches_and_rejects_tampered_ipa(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); work = root / '1.0.0-3'; work.mkdir()
            unsigned = work / 'artifact/ios-unsigned.ipa'; ipa(unsigned)
            signed = work / 'signed.ipa'; ipa(signed)
            state = {'repository': 'owner/repo', 'bundle': 'org.example.app', 'version': '1.0.0', 'number': '3',
                     'head': 'abc', 'run_id': 7, 'signed_sha256': release.hashlib.sha256(signed.read_bytes()).hexdigest()}
            (work / 'release.json').write_text(json.dumps(state))
            config = {'repository': 'owner/repo', 'workflow': 'ios.yml', 'bundle_id': 'org.example.app',
                      'state_directory': str(root), 'artifact_name': 'ios-{version}-{number}',
                      'sign_command': ['sign', '{unsigned}', '{signed}'],
                      'upload_command': ['upload', '{signed}'], 'finish_command': ['finish', '{work}']}
            cfg = root / 'config.json'; cfg.write_text(json.dumps(config))
            calls = []
            def fake_gh(repo, path, method='GET', body=None):
                calls.append((path, method))
                self.assertEqual(path, '/actions/runs/7'); self.assertEqual(method, 'GET')
                return {'head_sha': 'abc', 'status': 'completed', 'conclusion': 'success'}
            argv = ['release', '--config', str(cfg), '--version', '1.0.0', '--build-number', '3']
            with patch.object(sys, 'argv', argv), patch.object(release, 'gh', fake_gh), patch.object(release, 'command') as cmd:
                release.main()
                self.assertFalse(any(c.args[0][0] == 'sign' for c in cmd.call_args_list))
                self.assertTrue(any(c.args[0][0] == 'upload' for c in cmd.call_args_list))
            signed.write_bytes(b'tampered')
            with patch.object(sys, 'argv', argv), patch.object(release, 'gh', fake_gh), patch.object(release, 'command') as cmd:
                with self.assertRaises(ValueError): release.main()
                self.assertFalse(any(c.args[0][0] == 'upload' for c in cmd.call_args_list))

    def test_preflight_never_dispatches_or_uploads(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Path(d) / 'config.json'
            cfg.write_text(json.dumps({'repository': 'owner/repo', 'workflow': 'ios.yml',
                'sign_command': ['sign'], 'upload_command': ['upload'], 'finish_command': ['finish']}))
            with patch.object(sys, 'argv', ['release', '--config', str(cfg), '--version', '1.0.0', '--build-number', '3', '--check']), patch.object(release, 'command') as cmd, patch.object(release, 'gh', return_value={}) as gh:
                release.main()
                self.assertEqual(gh.call_args.args, ('owner/repo', '/actions/workflows/ios.yml'))
                self.assertEqual(cmd.call_count, 1)


if __name__ == '__main__': unittest.main()
