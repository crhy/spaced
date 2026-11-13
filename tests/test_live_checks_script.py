"""Argument and text checks for the 11.26.1 live-ISO check script.

These cases never start QEMU: every invocation below exits during argument
handling, so no VM, network, root, display or hardware is needed.
"""
from pathlib import Path
import shutil
import subprocess
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


if __name__ == '__main__':
    unittest.main()
