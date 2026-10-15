"""Issue #298: never install the X server that crashes the amdgpu driver."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / 'overlays/usr/lib/spaced-linux/spaced-update-apt-guard'
PIN = ROOT / 'overlays/etc/apt/preferences.d/spaced-xorg-abi'
BROKEN = '2:21.1.25-1devuan1'
FIXED = '2:21.1.25-1devuan1+spaced10.26.3'


def transaction(*actions):
    return 'VERSION 2\nAPT::Architecture=amd64\n\n' + ''.join(
        f'{package} {old} < {new} /var/cache/apt/archives/{package}.deb\n'
        for package, old, new in actions)


class GuardTests(unittest.TestCase):
    def run_guard(self, text):
        return subprocess.run(['bash', str(GUARD)], input=text,
                              capture_output=True, text=True, timeout=10)

    def test_broken_server_is_refused(self):
        result = self.run_guard(transaction(
            ('xserver-common', '2:21.1.24-1devuan1', BROKEN),
            ('xserver-xorg-core', '2:21.1.24-1devuan1', BROKEN)))
        self.assertEqual(result.returncode, 1)
        self.assertIn('AMD graphics', result.stderr)

    def test_broken_server_is_refused_without_an_epoch_too(self):
        result = self.run_guard(transaction(
            ('xserver-xorg-core', '21.1.24-1devuan1', BROKEN.split(':', 1)[1])))
        self.assertEqual(result.returncode, 1)

    def test_fixed_server_is_allowed(self):
        result = self.run_guard(transaction(
            ('xserver-common', BROKEN, FIXED),
            ('xserver-xorg-core', BROKEN, FIXED)))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_fixed_version_sorts_between_broken_and_devuan_fix(self):
        # Devuan's own fixed upload must replace ours without intervention.
        for lower, higher in ((BROKEN, FIXED), (FIXED, '2:21.1.25-2devuan1')):
            subprocess.run(['dpkg', '--compare-versions', lower, 'lt', higher], check=True)


@unittest.skipUnless(shutil.which('apt-cache'), 'requires apt-cache')
class PinTests(unittest.TestCase):
    def test_pin_blocks_exactly_the_broken_version(self):
        text = PIN.read_text()
        self.assertIn(f'Pin: version {BROKEN}\n', text)
        self.assertIn('Pin-Priority: -1', text)
        with tempfile.TemporaryDirectory() as temp:
            shutil.copy(PIN, temp)
            # APT rejects a malformed preferences file with an error.
            result = subprocess.run(
                ['apt-cache', '-o', f'Dir::Etc::PreferencesParts={temp}', 'policy'],
                capture_output=True, text=True, timeout=60)
            self.assertNotIn('E:', result.stderr)


if __name__ == '__main__':
    unittest.main()
