"""Issue #419: selected elogind updates remain a coordinated package set."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'overlays/usr/lib/spaced-linux/spaced-update-helper'
ELOGIND_SET = {'elogind', 'libelogind0', 'libelogind-compat', 'libpam-elogind'}


class ElogindSelectedUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)
        self.bin = self.state / 'bin'
        self.bin.mkdir()
        self.log = self.state / 'apt.log'
        guard = self.state / 'guard'
        guard.write_text('#!/bin/bash\nexit 0\n')
        guard.chmod(0o755)
        self.command('apt-get', 'printf "%s\\n" "$*" >> "$TEST_STATE/apt.log"')
        self.command('dpkg-query', '''
case "$*" in
  *uninstalled*) exit 1 ;;
  *) printf 'installed' ;;
esac
''')
        self.command('dpkg', '[[ ${1:-} == --audit ]] && exit 0; exit 0')
        self.command('apt-mark', 'exit 0')
        self.command('update-initramfs', 'exit 0')
        self.command('update-grub', 'exit 0')
        self.env = dict(
            os.environ,
            PATH=str(self.bin) + os.pathsep + os.environ['PATH'],
            TEST_STATE=str(self.state),
            SPACED_UPDATE_TEST='1',
            SPACED_UPDATE_TEST_SESSION_PAYLOAD=str(ROOT / 'overlays/usr/lib/spaced-linux/spaced-policy-rc.d'),
            SPACED_UPDATE_TEST_SESSION_POLICY=str(self.state / 'policy-rc.d'),
            SPACED_UPDATE_TEST_GUARD=str(guard),
        )

    def command(self, name, body):
        path = self.bin / name
        path.write_text('#!/bin/bash\n' + body + '\n')
        path.chmod(0o755)

    def run_helper(self, package):
        return subprocess.run(
            ['bash', str(HELPER), 'apt-install', package],
            env=self.env, capture_output=True, text=True, timeout=30)

    def install_plans(self):
        return [line for line in self.log.read_text().splitlines()
                if ' --only-upgrade --no-remove install ' in f' {line} ']

    def test_each_elogind_row_expands_to_all_installed_family_members(self):
        for selected in sorted(ELOGIND_SET):
            with self.subTest(selected=selected):
                self.log.unlink(missing_ok=True)
                result = self.run_helper(selected)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                plans = self.install_plans()
                self.assertGreaterEqual(len(plans), 3)
                for plan in plans:
                    words = set(plan.split())
                    self.assertTrue(ELOGIND_SET <= words, plan)

    def test_unrelated_selected_update_is_not_expanded(self):
        result = self.run_helper('mate-panel')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for plan in self.install_plans():
            self.assertIn('mate-panel', plan.split())
            self.assertTrue(ELOGIND_SET.isdisjoint(plan.split()), plan)


if __name__ == '__main__':
    unittest.main()
