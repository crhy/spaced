"""Issue #253: spaced-meta enables Samba user shares and grants sambashare.

Runs only the relevant blocks of the postinst, against scratch files and stub
commands, so nothing on the host is changed.
"""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
POSTINST = (ROOT / 'packages/spaced-meta/DEBIAN/postinst').read_text()

DEBIAN_SMB_CONF = """[global]
   workgroup = WORKGROUP
# Maximum number of usershare. 0 means that usershare is disabled.
#   usershare max shares = 100
   usershare allow guests = yes

[printers]
   comment = All Printers
"""


def block(start):
    match = re.search(rf'(?ms)^{re.escape(start)}.*?^fi$', POSTINST)
    assert match, f'postinst block not found: {start}'
    return match.group(0)


class UsershareTests(unittest.TestCase):
    def run_block(self, conf_text, action='configure'):
        with tempfile.TemporaryDirectory() as temp:
            conf = Path(temp) / 'smb.conf'
            conf.write_text(conf_text)
            script = block('smb_conf=').replace('/etc/samba/smb.conf', str(conf))
            subprocess.run(['sh', '-c', script, 'sh', action], check=True)
            return conf.read_text()

    def global_section(self, text):
        return text.split('[printers]')[0]

    def test_debian_default_gets_user_shares_enabled_once(self):
        once = self.run_block(DEBIAN_SMB_CONF)
        self.assertIn('   usershare max shares = 100\n', self.global_section(once))
        self.assertEqual(self.run_block(once), once)

    def test_administrator_value_is_kept(self):
        custom = DEBIAN_SMB_CONF.replace('[global]\n', '[global]\n   usershare max shares = 5\n')
        self.assertEqual(self.run_block(custom), custom)

    def test_trigger_runs_change_nothing(self):
        self.assertEqual(self.run_block(DEBIAN_SMB_CONF, 'triggered'), DEBIAN_SMB_CONF)


class SambashareGroupTests(unittest.TestCase):
    def test_desktop_users_join_once_and_service_accounts_do_not(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            bin_dir = temp / 'bin'
            bin_dir.mkdir()
            stubs = {
                'getent': 'case "$2" in sambashare) echo sambashare:x:995:;; '
                          'sudo) echo sudo:x:27:rhy,alice,svc;; esac',
                'id': 'case "$2" in rhy) echo 1000;; alice) echo 1001;; svc) echo 998;; *) exit 1;; esac',
                'usermod': 'echo "$*" >> "$LOG"',
            }
            for name, body in stubs.items():
                stub = bin_dir / name
                stub.write_text(f'#!/bin/sh\n{body}\n')
                stub.chmod(0o755)
            script = block('marker=').replace('/var/lib/spaced-linux', str(temp / 'state'))
            env = dict(os.environ, PATH=f'{bin_dir}:{os.environ["PATH"]}', LOG=str(temp / 'log'))
            for _ in range(2):
                subprocess.run(['sh', '-c', script, 'sh', 'configure'], check=True, env=env)
            self.assertEqual((temp / 'log').read_text().splitlines(),
                             ['-a -G sambashare rhy', '-a -G sambashare alice'])


if __name__ == '__main__':
    unittest.main()
