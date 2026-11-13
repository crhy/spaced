"""Argument and text checks for the issue #409 reboot-loop VM script.

These cases never start QEMU: every invocation exits during argument handling.
"""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/vm/qemu/reboot-loop.sh'


class RebootLoopScriptTests(unittest.TestCase):
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
        self.assertIn('Usage: reboot-loop.sh ISO [ROUNDS=5]',
                      result.stdout + result.stderr)

    def test_rejects_bad_round_count_and_missing_iso_without_booting(self):
        for args in (['/dev/null', '0'], ['/dev/null', 'many'], ['missing.iso', '3']):
            with self.subTest(args=args):
                result = self.run_script(*args)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertNotIn('QEMU PID', result.stdout)

    def test_guest_reboots_are_not_disabled(self):
        """A -no-reboot guest can never show the crash or a real reboot."""
        text = SCRIPT.read_text(encoding='utf-8')
        self.assertNotIn('-no-reboot', text)
        self.assertIn('-boot order=d', text)
        self.assertIn('org.freedesktop.login1.Manager.Reboot', text)
        self.assertIn('org.freedesktop.login1.Manager.PowerOff', text)

    def test_cleanup_kills_only_recorded_processes(self):
        text = SCRIPT.read_text(encoding='utf-8')
        self.assertNotIn('pkill -f', text)
        self.assertIn('trap cleanup EXIT', text)
        self.assertIn('QEMU_PID=$!', text)


if __name__ == '__main__':
    unittest.main()
