"""Argument, text and pure-logic checks for the v04 real-upgrade VM script.

These cases never start QEMU or a web server: every invocation below exits
during argument handling, and the source-rewrite program shipped inside the
script is exercised against a throwaway directory instead of /etc/apt.  No VM,
network, root, display or hardware is needed.
"""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/vm/qemu/upgrade-test.sh'
ISO = 'build/iso/spaced-linux-11.26-amd64.iso'
SHIPPED_SOURCE = ROOT / 'overlays/etc/apt/sources.list.d/spaced-apt.list'


def rewrite_program():
    """The python program the script pipes to the guest's python3."""
    lines = SCRIPT.read_text(encoding='utf-8').splitlines()
    start = next(index for index, line in enumerate(lines)
                 if line.startswith('# BEGIN SOURCE REWRITE'))
    end = next(index for index, line in enumerate(lines)
               if line.startswith('# END SOURCE REWRITE'))
    return '\n'.join(lines[start + 1:end]) + '\n'


class UpgradeTestScriptTests(unittest.TestCase):
    def run_script(self, *args):
        return subprocess.run(['bash', str(SCRIPT), *args], text=True,
                              capture_output=True, timeout=60)

    def run_rewrite(self, apt_dir, *args):
        workspace = Path(tempfile.mkdtemp(prefix='spaced-v04-rewrite-'))
        try:
            program = workspace / 'rewrite.py'
            program.write_text(rewrite_program(), encoding='utf-8')
            return subprocess.run(['python3', str(program), *args, str(apt_dir)],
                                  text=True, capture_output=True, timeout=30)
        finally:
            shutil.rmtree(workspace, ignore_errors=True)

    def make_apt_dir(self):
        apt_dir = Path(tempfile.mkdtemp(prefix='spaced-v04-apt-'))
        (apt_dir / 'sources.list.d').mkdir()
        shutil.copy(SHIPPED_SOURCE, apt_dir / 'sources.list.d' / 'spaced-apt.list')
        (apt_dir / 'sources.list').write_text(
            'deb http://deb.devuan.org/merged ceres main contrib non-free non-free-firmware\n',
            encoding='utf-8')
        return apt_dir

    def test_script_exists_and_parses(self):
        self.assertTrue(SCRIPT.is_file(), f'missing {SCRIPT}')
        result = subprocess.run(['bash', '-n', str(SCRIPT)], text=True,
                                capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_usage_without_arguments(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 2)
        self.assertIn('Usage: upgrade-test.sh OLD_ISO REPO_DIR', result.stdout + result.stderr)

    def test_usage_without_repository_argument(self):
        result = self.run_script(ISO)
        self.assertEqual(result.returncode, 2)
        self.assertIn('Usage: upgrade-test.sh OLD_ISO REPO_DIR', result.stdout + result.stderr)

    def test_missing_iso_is_rejected_without_booting(self):
        result = self.run_script('does-not-exist.iso', 'spaced-apt')
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn('ISO not found', result.stdout + result.stderr)
        self.assertNotIn('QEMU PID', result.stdout)

    def test_missing_repository_directory_is_rejected(self):
        result = self.run_script(ISO, 'no-such-repo-dir')
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn('Repository directory not found', result.stdout + result.stderr)
        self.assertNotIn('HTTP server PID', result.stdout)

    def test_unsigned_repository_directory_is_rejected(self):
        workspace = Path(tempfile.mkdtemp(prefix='spaced-v04-repo-'))
        try:
            result = self.run_script(ISO, str(workspace))
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn('signed spaced repository is missing', result.stdout + result.stderr)
            self.assertNotIn('HTTP server PID', result.stdout)
        finally:
            shutil.rmtree(workspace, ignore_errors=True)

    def test_shellcheck_is_clean(self):
        shellcheck = shutil.which('shellcheck')
        if shellcheck is None:
            self.skipTest('shellcheck is not installed')
        result = subprocess.run([shellcheck, str(SCRIPT)], text=True,
                                capture_output=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_headless_vm_and_server_stopped_by_recorded_pid(self):
        text = SCRIPT.read_text(encoding='utf-8')
        self.assertNotIn('pkill', text)
        self.assertNotIn('-display gtk', text)
        self.assertIn('-display none', text)
        self.assertIn('trap cleanup EXIT', text)
        self.assertIn('QEMU_PID=$!', text)
        self.assertIn('HTTP_PID=$!', text)
        self.assertIn('kill "$HTTP_PID"', text)
        self.assertIn('kill "$QEMU_PID"', text)

    def test_candidate_repository_is_served_on_the_host_loopback(self):
        text = SCRIPT.read_text(encoding='utf-8')
        self.assertIn('python3 -m http.server', text)
        self.assertIn('--bind 127.0.0.1', text)
        self.assertIn('--directory "$REPO_DIR"', text)
        # QEMU user networking: the guest reaches the host loopback via 10.0.2.2.
        self.assertIn('http://10.0.2.2:', text)
        self.assertIn('SPACED_REPO_HTTP_PORT:-8930', text)

    def test_upgrade_runs_the_old_systems_own_updater(self):
        text = SCRIPT.read_text(encoding='utf-8')
        self.assertIn('/usr/lib/spaced-linux/spaced-update-helper', text)
        self.assertIn('export DEBIAN_FRONTEND=noninteractive', text)
        self.assertIn('SPACED_UPGRADE_TIMEOUT:-2400', text)
        # Only if that helper is not runnable in the old image: the plain
        # non-interactive full-upgrade named in the task.
        self.assertIn('apt-get -y -o Dpkg::Options::=--force-confold full-upgrade', text)

    def test_guest_is_an_8_gigabyte_live_system(self):
        text = SCRIPT.read_text(encoding='utf-8')
        self.assertIn('SPACED_QEMU_RAM:-8192', text)
        self.assertIn('-m "$RAM"', text)

    def test_source_rewrite_changes_only_the_url(self):
        apt_dir = self.make_apt_dir()
        try:
            result = self.run_rewrite(apt_dir, 'spaced', 'http://10.0.2.2:8930')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            source = (apt_dir / 'sources.list.d' / 'spaced-apt.list').read_text(encoding='utf-8')
            self.assertIn(
                'deb [signed-by=/usr/share/keyrings/spaced-archive-keyring.gpg] '
                'http://10.0.2.2:8930 spaced main', source)
            self.assertNotIn('crhy.github.io', source)
            # Comments, suite, component and signed-by are kept exactly.
            self.assertEqual(len(source.splitlines()),
                             len(SHIPPED_SOURCE.read_text(encoding='utf-8').splitlines()))
            devuan = (apt_dir / 'sources.list').read_text(encoding='utf-8')
            self.assertEqual(devuan,
                             'deb http://deb.devuan.org/merged ceres main contrib '
                             'non-free non-free-firmware\n')
        finally:
            shutil.rmtree(apt_dir, ignore_errors=True)

    def test_source_rewrite_refuses_to_guess(self):
        apt_dir = self.make_apt_dir()
        try:
            # A suite that no Spaced line uses must not be rewritten at all.
            result = self.run_rewrite(apt_dir, 'spaced-testing', 'http://10.0.2.2:8930')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('changed=0', result.stdout)
            source = (apt_dir / 'sources.list.d' / 'spaced-apt.list').read_text(encoding='utf-8')
            self.assertIn('crhy.github.io', source)
        finally:
            shutil.rmtree(apt_dir, ignore_errors=True)

    def test_reports_one_line_per_check_and_a_result(self):
        text = SCRIPT.read_text(encoding='utf-8')
        self.assertIn('echo "PASS: $1"', text)
        self.assertIn('echo "FAIL: $1"', text)
        self.assertIn('RESULT: PASS passed=$PASSED failed=$FAILED', text)
        self.assertIn('RESULT: FAIL passed=$PASSED failed=$FAILED', text)
        self.assertIn('INFO:', text)
        for marker in ('/etc/os-release', 'spaced-meta', 'dpkg --audit', 'apt-get check',
                       'elogind', 'anacron', '60spaced-transaction-guard', 'gparted',
                       'testdisk photorec gddrescue smartmontools lvm2 exfatprogs',
                       'segfault'):
            self.assertIn(marker, text)


if __name__ == '__main__':
    unittest.main()
