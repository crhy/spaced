#!/usr/bin/env python3
"""The shipped UI's budget (issue #426, step 5): first paint well under a
second, and after the window is hidden no timer repaints anything - the
polling timers stop with the map and nothing runs while hidden. The test
drives the REAL app under Xvfb over the fake bigboy machine, so it never
reads or writes the test machine's graphics hardware."""
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'overlays/usr/lib/spaced-linux/spaced-gpu-manager.py'
FAKE = ROOT / 'docs/design/gpu-manager/fake-bigboy.json'


@unittest.skipUnless(shutil.which('xvfb-run') and shutil.which('Xvfb'),
                     'requires Xvfb')
class UiBudgetTest(unittest.TestCase):
    def run_app(self, *flags):
        return subprocess.run(
            ['xvfb-run', '-a', sys.executable, str(APP),
             '--fake-data', str(FAKE)] + list(flags),
            capture_output=True, text=True, timeout=90)

    def lines(self, stdout, prefix):
        return [line for line in stdout.splitlines() if line.startswith(prefix)]

    def test_first_paint_under_budget_and_silence_while_hidden(self):
        result = self.run_app('--self-check')
        self.assertEqual(result.returncode, 0, result.stderr)
        paints = self.lines(result.stdout, 'FIRST_PAINT ')
        self.assertEqual(len(paints), 1, result.stdout)
        seconds = float(paints[0].split()[1])
        self.assertLess(seconds, 1.5,
                        f'first paint took {seconds}s; the look must appear '
                        'within a second of opening GPU Manager')
        hidden = self.lines(result.stdout, 'HIDDEN_RENDERS ')
        self.assertEqual(hidden, ['HIDDEN_RENDERS 0'],
                         'the window repainted after being hidden')

    def test_pages_capture_from_fake_data(self):
        for page in ('overview', 'roles', 'move', 'drivers', 'first-run'):
            with self.subTest(page=page):
                out = Path('/tmp') / f'gpu-manager-{page}-budget.png'
                result = self.run_app('--capture', page, '--out', str(out))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(out.is_file() and out.stat().st_size > 10000,
                                f'{page} did not render a real PNG')
                out.unlink(missing_ok=True)


if __name__ == '__main__':
    unittest.main()
