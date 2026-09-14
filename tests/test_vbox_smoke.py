"""Statically exercise the VirtualBox smoke launcher without booting any VM.

Only early-exit paths are executed (--help, bad graphics profile, missing
ISO); every case returns before VBoxManage creates anything. Content
assertions cover the issue #218 requirements (graphics profiles, distinct
no-window-manager reporting, installer launch check).
"""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/vm/virtualbox/smoke-iso.sh'
TEXT = SCRIPT.read_text(encoding='utf-8')


def run_script(*args, env_extra=None):
    env = dict(os.environ, SPACED_VBOX_SSH_PORT='65531',
               SPACED_ISO_SMOKE_TIMEOUT='2',
               SPACED_VBOX_FIRMWARE='bios')
    env.update(env_extra or {})
    return subprocess.run([str(SCRIPT), *args], env=env, text=True,
                          capture_output=True, timeout=20)


def vms_snapshot():
    try:
        result = subprocess.run(['VBoxManage', 'list', 'vms'], text=True,
                                capture_output=True, timeout=20)
        return result.stdout
    except OSError:
        return None


class VBoxSmokeStaticTests(unittest.TestCase):
    def test_help_exits_zero(self):
        result = run_script('--help')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--graphics', result.stdout)

    def test_bad_graphics_profile_is_rejected_before_any_vm_work(self):
        before = vms_snapshot()
        result = run_script('--graphics', 'bogus', '/nonexistent.iso')
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('default', result.stderr)
        self.assertIn('vboxsvga', result.stderr)
        self.assertEqual(vms_snapshot(), before)

    def test_bad_graphics_env_is_rejected(self):
        result = run_script('/nonexistent.iso',
                            env_extra={'SPACED_VBOX_GRAPHICS': 'svga3d'})
        self.assertEqual(result.returncode, 2, result.stderr)

    def test_missing_iso_fails_without_vm_side_effects(self):
        before = vms_snapshot()
        result = run_script('/nonexistent.iso')
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(vms_snapshot(), before)

    def test_equals_form_profile_flag_is_rejected_for_bad_values(self):
        result = run_script('--graphics=bogus', '/nonexistent.iso')
        self.assertEqual(result.returncode, 2, result.stderr)

    def test_two_isos_are_rejected(self):
        result = run_script('/a.iso', '/b.iso')
        self.assertEqual(result.returncode, 2, result.stderr)

    def test_extra_args_after_separator_are_rejected(self):
        result = run_script('--', '/a.iso', '/b.iso')
        self.assertEqual(result.returncode, 2, result.stderr)

    def test_both_graphics_profiles_supported(self):
        self.assertIn('SPACED_VBOX_GRAPHICS', TEXT)
        self.assertIn('--graphicscontroller vboxsvga --accelerate-3d off', TEXT)
        # The `default` profile must not force a controller: VirtualBox's own
        # ostype defaults (VMSVGA) have to apply.
        self.assertIn('showvminfo', TEXT)
        self.assertIn('--machinereadable', TEXT)
        self.assertIn('graphicscontroller', TEXT)

    def test_no_window_manager_result_is_distinct(self):
        self.assertIn('NO_WM_EXIT=3', TEXT)
        self.assertIn('NO_WINDOW_MANAGER', TEXT)
        self.assertIn('spaced-window-manager', TEXT)
        self.assertIn('wmctrl -m', TEXT)
        self.assertIn('exit "$NO_WM_EXIT"', TEXT)

    def test_installer_launch_check_present(self):
        self.assertIn('/usr/local/bin/install-spaced-linux', TEXT)
        self.assertIn('INSTALLER_TIMEOUT=90', TEXT)
        self.assertIn('wmctrl -l', TEXT)
        self.assertIn('xdotool search --name', TEXT)
        self.assertIn('capture_screenshot_to', TEXT)

    def test_makefile_exposes_both_targets(self):
        makefile = (ROOT / 'Makefile').read_text(encoding='utf-8')
        self.assertIn('vbox-smoke:', makefile)
        self.assertIn('vbox-smoke-default:', makefile)


if __name__ == '__main__':
    unittest.main()
