"""Argument and text checks for the 11.26.1 live-ISO check script.

These cases never start QEMU: every invocation below exits during argument
handling, so no VM, network, root, display or hardware is needed.
"""
from pathlib import Path
import os
import re
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/vm/qemu/live-checks.sh'


class LiveChecksScriptTests(unittest.TestCase):
    def run_script(self, *args):
        return subprocess.run(['bash', str(SCRIPT), *args], text=True,
                              capture_output=True, timeout=30)

    def test_script_exists_and_parses(self):
        self.assertTrue(SCRIPT.is_file(), f'missing {SCRIPT}')
        result = subprocess.run(['bash', '-n', str(SCRIPT)], text=True,
                                capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_usage_without_arguments(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 2)
        self.assertIn('Usage: live-checks.sh ISO', result.stdout + result.stderr)

    def test_missing_iso_is_rejected_without_booting(self):
        result = self.run_script('does-not-exist.iso')
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn('ISO not found', result.stdout + result.stderr)
        self.assertNotIn('QEMU PID', result.stdout)

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

    def test_headless_vm_stopped_by_recorded_pid(self):
        text = SCRIPT.read_text(encoding='utf-8')
        self.assertNotIn('pkill -f', text)
        self.assertNotIn('-display gtk', text)
        self.assertIn('-display none', text)
        self.assertIn('trap cleanup EXIT', text)
        self.assertIn('QEMU_PID=$!', text)

    def test_reports_one_line_per_check_and_a_result(self):
        text = SCRIPT.read_text(encoding='utf-8')
        self.assertIn('echo "PASS: $name"', text)
        self.assertIn('echo "FAIL: $name', text)
        self.assertIn('RESULT: PASS passed=$PASSED failed=$FAILED', text)
        self.assertIn('RESULT: FAIL passed=$PASSED failed=$FAILED', text)
        self.assertIn('INFO:', text)

    def probe_source(self):
        text = SCRIPT.read_text(encoding='utf-8')
        match = re.search(r"IDLE_PROBE=\$\(cat <<'PY'\n(.*?)\nPY\n\)", text, re.S)
        self.assertIsNotNone(match, 'the idle probe is missing from live-checks.sh')
        return match.group(1)

    def test_idle_window_measures_a_settled_desktop_with_limits(self):
        # r02 measured a 6-12 % "idle" CPU that was only the login burst: the
        # window must start after a settle delay and must have hard limits.
        text = SCRIPT.read_text(encoding='utf-8')
        self.assertIn('IDLE_SETTLE_SECONDS=${SPACED_LIVE_IDLE_SETTLE_SECONDS:-60}', text)
        self.assertIn('IDLE_WINDOW_SECONDS=${SPACED_LIVE_IDLE_WINDOW_SECONDS:-60}', text)
        self.assertIn('IDLE_CPU_LIMIT=${SPACED_LIVE_IDLE_CPU_LIMIT:-5}', text)
        self.assertIn('IDLE_RCHAR_LIMIT=${SPACED_LIVE_IDLE_RCHAR_LIMIT:-1024}', text)
        settle = text.index('sleep "$IDLE_SETTLE_SECONDS"')
        window = text.index('python3 - $IDLE_WINDOW_SECONDS')
        self.assertLess(settle, window)
        self.assertIn('k: live desktop idle CPU', text)
        self.assertIn('k: spaced-theme-monitor reads', text)

    def test_idle_probe_measures_cpu_context_switches_and_monitor_reads(self):
        source = self.probe_source()
        for marker in ('/proc/stat', "line.startswith('ctxt ')",
                       "'spaced-theme-monitor' not in cmd", "line.startswith('rchar:')"):
            self.assertIn(marker, source)
        # Nothing in the measured window may fork or touch the guest: the probe
        # only reads /proc and sleeps.
        for forbidden in ('import subprocess', 'os.system', 'Popen', 'os.chmod',
                          'os.remove', 'apt-get', 'gsettings', 'systemctl'):
            self.assertNotIn(forbidden, source)

    @unittest.skipUnless(Path('/proc/stat').is_file(), 'needs /proc')
    def test_idle_probe_runs_and_reports_its_numbers(self):
        source = self.probe_source()
        result = subprocess.run([sys.executable, '-', '1'], input=source, text=True,
                                capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for key in ('idle_cpu_percent=', 'context_switches_per_s=',
                    'theme_monitor_rchar_per_s=', 'theme_monitor_processes='):
            self.assertIn(key, result.stdout)
        cpu = float(re.search(r'idle_cpu_percent=([0-9.]+)', result.stdout)[1])
        self.assertGreaterEqual(cpu, 0.0)
        self.assertLessEqual(cpu, 100.0)


if __name__ == '__main__':
    unittest.main()
