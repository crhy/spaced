"""Argument, text and pure-logic checks for the v04 real-upgrade VM script.

These cases never start QEMU or a web server: every invocation below exits
during argument handling, and the source-rewrite program shipped inside the
script is exercised against a throwaway directory instead of /etc/apt.  No VM,
network, root, display or hardware is needed.
"""
from pathlib import Path
import atexit
import re
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/vm/qemu/upgrade-test.sh'
# A placeholder is enough: these tests only exercise argument checking, and
# must not depend on a release image being present under build/.
_ISO_DIR = tempfile.mkdtemp(prefix='spaced-upgrade-iso-')
ISO = str(Path(_ISO_DIR) / 'placeholder.iso')
Path(ISO).write_bytes(b'')
atexit.register(shutil.rmtree, _ISO_DIR, ignore_errors=True)
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
    def test_audio_survival_rejects_missing_or_replaced_state(self):
        source = SCRIPT.read_text()
        function = re.search(r'^audio_survived\(\) \{\n.*?^\}', source,
                             re.MULTILINE | re.DOTALL).group(0)
        baseline = 'boot=uuid\nruntime=1:2\nsocket=1:3\npulse=42\n'
        cases = [(baseline, baseline, 0), ('', '', 1),
                 (baseline, '', 1),
                 (baseline, baseline.replace('pulse=42', 'pulse=43'), 1),
                 (baseline, baseline.replace('socket=1:3', 'socket=1:4'), 1),
                 (baseline, baseline.replace('runtime=1:2', 'runtime=1:5'), 1),
                 (baseline, baseline.replace('boot=uuid', 'boot=new'), 1)]
        with tempfile.TemporaryDirectory() as directory:
            before = Path(directory) / 'before'
            after = Path(directory) / 'after'
            for old, new, expected in cases:
                with self.subTest(old=old, new=new):
                    before.write_text(old)
                    after.write_text(new)
                    result = subprocess.run(
                        ['bash', '-c', function + '\naudio_survived "$1" "$2"',
                         'test', str(before), str(after)], capture_output=True,
                        text=True, timeout=5)
                    self.assertEqual(result.returncode, expected, result.stderr)

    def test_audio_probe_does_not_repair_away_the_failure(self):
        source = SCRIPT.read_text()
        probe = source.split("<<'AUDIO'\n", 1)[1].split('\nAUDIO', 1)[0]
        self.assertIn('test -S "$socket"', probe)
        self.assertIn('su -s /bin/sh user', probe)
        self.assertIn('pactl --server=unix:$socket info', probe)
        self.assertNotIn('pulseaudio --start', probe)
        self.assertNotIn('kill ', probe)
        self.assertLess(source.index('while ! audio_state'),
                        source.index('UPGRADE_STATUS=$(run_guest_upgrade'))

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
        # The scripts are kept clean against shellcheck 0.10+; older releases
        # (for example 0.9 on CI runners) report differently.
        version = subprocess.run([shellcheck, '--version'], text=True,
                                 capture_output=True, timeout=30).stdout
        found = re.search(r'version: (\d+)\.(\d+)', version)
        if not found or (int(found[1]), int(found[2])) < (0, 10):
            self.skipTest('shellcheck 0.10 or newer is required')
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

    def test_live_overlay_retry_is_exact_and_uses_candidate_helper(self):
        text = SCRIPT.read_text(encoding='utf-8')
        self.assertIn("failed to get canonical path of .overlay.", text)
        self.assertIn("grep -qE '^SPACED_STEP:65:'", text)
        self.assertIn("Skipping GRUB refresh for the live overlay root.", text)
        self.assertIn('run_guest_upgrade "$HELPER all" upgrade-retry', text)
        self.assertIn('candidate_helper_retry_status=', text)

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
