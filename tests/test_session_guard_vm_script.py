"""Checks for the VM guard harness; never starts a VM or touches services."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/vm/qemu/session-guard-test.sh'


class SessionGuardHarnessTests(unittest.TestCase):
    def test_audio_comparison_requires_original_healthy_socket(self):
        source = SCRIPT.read_text()
        functions = '\n'.join(re.search(
            rf'^{name}\(\) \{{\n.*?^\}}', source, re.M | re.S).group()
            for name in ('value', 'check_audio_survived'))
        baseline = ('runtime_inode=1:2\npulse_socket_inode=1:3\n'
                    'pulse_pid=42\npulse_reachable=yes\n')
        with tempfile.TemporaryDirectory() as directory:
            before = Path(directory) / 'B-before.txt'
            after = Path(directory) / 'B-after.txt'
            for old, new, expected in (
                (baseline, baseline, 'PASS'),
                ('', '', 'FAIL'),
                (baseline, baseline.replace('1:3', '1:4'), 'FAIL'),
                (baseline, baseline.replace('1:2', '1:5'), 'FAIL'),
                (baseline, baseline.replace('42', '43'), 'FAIL'),
                (baseline.replace('yes', 'no'), baseline.replace('yes', 'no'), 'FAIL'),
            ):
                with self.subTest(old=old, new=new):
                    before.write_text(old)
                    after.write_text(new)
                    result = subprocess.run(
                        ['bash', '-c', 'OUT=$1\npass() { echo PASS; }\n'
                         'fail() { echo FAIL; }\n' + functions +
                         '\ncheck_audio_survived after', 'test', directory],
                        capture_output=True, text=True, timeout=5)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout.strip(), expected)

    def test_local_reinstall_is_not_a_noop(self):
        self.assertIn('apt-get install --reinstall -y /var/tmp/spaced-g01/',
                      SCRIPT.read_text())

    def test_baseline_version_can_differ_from_candidate(self):
        self.assertIn('EXPECTED_VERSION=${SPACED_EXPECTED_VERSION:-', SCRIPT.read_text())

    def test_unavailable_transaction_cannot_pass(self):
        self.assertIn("fail 'round B package transaction unavailable:", SCRIPT.read_text())
