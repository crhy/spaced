"""Issue #297: Windows 10/11 sign in to shares with a Samba password."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'overlays/usr/lib/spaced-linux/spaced-samba-password-helper'
POLICY = ROOT / 'overlays/usr/share/polkit-1/actions/com.spacedlinux.sharing.policy'


class HelperTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.temp = Path(temp.name)
        bin_dir = self.temp / 'bin'
        bin_dir.mkdir()
        self.log = self.temp / 'log'
        stubs = {
            'id': 'echo "${FAKE_UID:-0}"',
            'getent': 'case "$2" in 1000) echo "rhy:x:1000:1000::/home/rhy:/bin/bash";; esac',
            'smbpasswd': 'printf "args %s\\n" "$*" >> "$LOG"; cat >> "$LOG"',
        }
        for name, body in stubs.items():
            (bin_dir / name).write_text(f'#!/bin/sh\n{body}\n')
            (bin_dir / name).chmod(0o755)
        self.env = dict(os.environ, PATH=f'{bin_dir}:{os.environ["PATH"]}', LOG=str(self.log))

    def run_helper(self, password='s3cret pass', args=(), **env):
        return subprocess.run(['bash', str(HELPER), *args], input=password + '\n',
                              env=dict(self.env, **env), capture_output=True,
                              text=True, timeout=10)

    def logged(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def test_sets_and_enables_the_pkexec_caller(self):
        result = self.run_helper(PKEXEC_UID='1000')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.logged(), ['args -s -a rhy', 's3cret pass', 's3cret pass',
                                         'args -e rhy'])

    def test_refuses_unprivileged_runs_arguments_and_service_accounts(self):
        cases = [dict(FAKE_UID='1000', PKEXEC_UID='1000'),
                 dict(PKEXEC_UID='0'), dict(PKEXEC_UID='998'), dict(PKEXEC_UID='1abc'),
                 dict(PKEXEC_UID='1001'), dict()]
        for env in cases:
            self.assertNotEqual(self.run_helper(**env).returncode, 0, env)
        self.assertNotEqual(self.run_helper(args=('root',), PKEXEC_UID='1000').returncode, 0)
        self.assertNotEqual(self.run_helper(password='', PKEXEC_UID='1000').returncode, 0)
        self.assertEqual(self.logged(), [])

    def test_policy_names_the_helper_and_needs_an_active_admin(self):
        text = POLICY.read_text()
        self.assertIn(f'>/usr/lib/spaced-linux/{HELPER.name}<', text)
        self.assertIn('<allow_any>no</allow_any>', text)
        self.assertIn('<allow_active>auth_admin_keep</allow_active>', text)


if __name__ == '__main__':
    unittest.main()
