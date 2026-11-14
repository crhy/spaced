"""Argument and text checks for the 11.26.1 release-screenshot script.

These cases never start QEMU: every invocation below exits during argument
handling, so no VM, network, root, display or hardware is needed.
"""
from pathlib import Path
import re
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/vm/qemu/release-shots.sh'

# The six release shots; the names are also the published file names.
SHOTS = (
    'desktop-dark',
    'spaced-monitor',
    'spaced-welcome',
    'caja-set-wallpaper',
    'live-rescue-gparted',
    'spaced-update-os-release',
)


class ReleaseShotsScriptTests(unittest.TestCase):
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
        self.assertIn('Usage: release-shots.sh ISO', result.stdout + result.stderr)

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
        self.assertIn('-qmp "unix:$QMP_SOCKET,server=on,wait=off"', text)

    def test_refuses_to_run_without_kvm_or_pillow(self):
        text = SCRIPT.read_text(encoding='utf-8')
        self.assertIn('/dev/kvm', text)
        self.assertIn("python3 -c 'from PIL import Image'", text)

    def test_all_six_release_shots_are_taken(self):
        text = SCRIPT.read_text(encoding='utf-8')
        for name in SHOTS:
            self.assertIn(f"take_shot {name} ", text, f'no shot named {name}')

    def test_shots_are_measured_and_converted_to_webp(self):
        text = SCRIPT.read_text(encoding='utf-8')
        self.assertIn("'screendump'", text)
        self.assertIn("im.save(webp, 'WEBP', quality=90, method=6)", text)
        # A black or flat frame must never be published: both measurements gate.
        self.assertIn('if std <= 10.0:', text)
        self.assertIn('if black >= 0.30:', text)
        # ... and a bad frame is retaken instead of accepted.
        self.assertIn('is not drawn yet', text)

    def test_images_are_published_under_docs_releases(self):
        text = SCRIPT.read_text(encoding='utf-8')
        self.assertIn('docs/releases/$RELEASE_VERSION/images', text)
        self.assertIn('README.md', text)
        # A stale image of an older run must not survive a new run.
        self.assertIn('rm -f "$DOCS_DIR"/shot-*.png', text)

    def test_guest_desktop_is_set_to_full_hd(self):
        text = SCRIPT.read_text(encoding='utf-8')
        self.assertIn('xrandr --output $OUTPUT --mode ${XRES}x${YRES}', text)
        self.assertIn('XRES=${SPACED_SHOTS_XRES:-1920}', text)
        self.assertIn('YRES=${SPACED_SHOTS_YRES:-1080}', text)

    def test_never_touches_the_iso_or_the_host_desktop(self):
        text = SCRIPT.read_text(encoding='utf-8')
        # The VM is headless; the host must never be given an X display.
        self.assertNotIn('-display gtk', text)
        self.assertNotIn('export DISPLAY', text)
        for line in text.splitlines():
            if 'build/iso' in line and not line.lstrip().startswith('#'):
                self.fail(f'the script must not write into build/iso: {line}')


if __name__ == '__main__':
    unittest.main()
