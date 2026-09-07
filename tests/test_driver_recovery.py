"""Driver recovery behavior with temporary configuration and mocked host commands."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import sys
import types
import unittest
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).parents[1]
LIB = ROOT / "overlays/usr/lib/spaced-linux"
spec = importlib.util.spec_from_file_location("driver_config", LIB / "spaced-nvidia-config.py")
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)


class ConfigurationRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "root"
        self.root.mkdir()
        self.manifest = Path(self.temp.name) / "transaction.json"

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def test_restore_changes_only_and_preserve_unrelated_new_files(self):
        old = self.write("etc/modprobe.d/driver.conf", "blacklist nvidia\n")
        grub = self.write("etc/default/grub", "original boot arguments\n")
        config.backup(self.root, self.manifest)
        old.write_text("# disabled blacklist nvidia\n")
        grub.write_text("new boot arguments\n")
        policy = self.write("etc/modprobe.d/zz-spaced-nvidia.conf", "blacklist nouveau\n")
        config.capture(self.root, self.manifest)
        unrelated = self.write("etc/modprobe.d/new-audio.conf", "options snd-hda-intel power_save=1\n")
        launcher = self.write("usr/local/bin/spaced-window-manager", "new maintained launcher\n")
        self.assertTrue(config.restore(self.root, self.manifest))
        self.assertEqual(old.read_text(), "blacklist nvidia\n")
        self.assertEqual(grub.read_text(), "original boot arguments\n")
        self.assertFalse(policy.exists())
        self.assertEqual(unrelated.read_text(), "options snd-hda-intel power_save=1\n")
        self.assertEqual(launcher.read_text(), "new maintained launcher\n")
        self.assertTrue(config.restore(self.root, self.manifest))
        self.assertEqual(self.manifest.stat().st_mode & 0o777, 0o600)

    def test_later_admin_changes_survive_and_make_recovery_incomplete(self):
        grub = self.write("etc/default/grub", "original\n")
        config.backup(self.root, self.manifest)
        grub.write_text("installer\n")
        config.capture(self.root, self.manifest)
        grub.write_text("administrator edited after install\n")
        self.assertFalse(config.restore(self.root, self.manifest))
        self.assertEqual(grub.read_text(), "administrator edited after install\n")

    def test_removed_xorg_symlink_is_restored_without_replacing_target(self):
        target = self.write("etc/X11/custom.conf", "custom configuration\n")
        link = self.root / "etc/X11/xorg.conf"
        link.symlink_to("custom.conf")
        config.backup(self.root, self.manifest)
        link.unlink()
        config.capture(self.root, self.manifest)
        self.assertTrue(config.restore(self.root, self.manifest))
        self.assertEqual(os.readlink(link), "custom.conf")
        self.assertEqual(target.read_text(), "custom configuration\n")

    def test_missing_after_record_fails_without_deleting_anything(self):
        grub = self.write("etc/default/grub", "original\n")
        config.backup(self.root, self.manifest)
        with self.assertRaisesRegex(ValueError, "No completed"):
            config.restore(self.root, self.manifest)
        self.assertEqual(grub.read_text(), "original\n")


class DriverHelperTests(unittest.TestCase):
    def run_helper(self, action, failure=""):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / "run"
            run.mkdir()
            (run / "packages-before.txt").write_text("base-package\n")
            (run / "driver-versions-before.txt").write_text("")
            pending = root / "pending"
            pending.touch()
            helper = root / "helper"
            # Redirect even the absolute reboot command before sourcing any code.
            helper.write_text((LIB / "spaced-nvidia-helper").read_text().replace("/sbin/reboot", "mock_reboot"))
            runner = r'''
dpkg() { printf 'amd64\n'; }
source "$TEST_HELPER"
RUN_DIR="$TEST_ROOT/run"
PENDING_FILE="$TEST_ROOT/pending"
RECOVERED_FILE="$TEST_ROOT/recovered"
CURRENT_RUN_FILE="$TEST_ROOT/current"
KERNEL=test-kernel
TRANSACTION_ACTIVE=0
REBOOT_AFTER=1
mock_command() {
    printf 'CALL:%s\n' "$*"
    [ "$1" != "$TEST_FAILURE" ]
}
dpkg() { mock_command dpkg "$@"; }
apt-get() { mock_command apt-get "$@"; }
update-initramfs() { mock_command update-initramfs "$@"; }
update-grub() { mock_command update-grub "$@"; }
update-glx() { mock_command update-glx "$@"; }
dconf() { mock_command dconf "$@"; }
sync() { :; }
mock_reboot() { printf 'REBOOT_CALLED\n'; }
restore_configuration() { mock_command restore_configuration; }
record_configuration_changes() { mock_command record_configuration_changes; }
record_new_nvidia_packages() { printf 'nvidia-new\n' > "$RUN_DIR/new-nvidia-packages.txt"; }
modprobe() {
    if [ "$1" = --showconfig ]; then
        printf 'blacklist nouveau\n'
    else
        printf 'install /bin/false\n'
    fi
}
'''
            script = root / "run.sh"
            script.write_text(runner + "\n" + action)
            env = os.environ.copy()
            env.update(TEST_ROOT=str(root), TEST_HELPER=str(helper), TEST_FAILURE=failure)
            result = subprocess.run(["bash", str(script)], env=env, text=True, capture_output=True)
            return result, pending.exists()

    def test_successful_recovery_clears_marker_and_may_reboot(self):
        result, pending = self.run_helper("rollback_transaction 30")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("SPACED_SUCCESS:restored", result.stdout)
        self.assertIn("REBOOT_CALLED", result.stdout)
        self.assertFalse(pending)

    def test_failed_steps_report_partial_recovery_without_reboot(self):
        for command in ("apt-get", "restore_configuration", "update-initramfs", "update-grub", "dconf"):
            with self.subTest(command=command):
                result, pending = self.run_helper("rollback_transaction 30", command)
                self.assertEqual(result.returncode, 52, result.stdout + result.stderr)
                self.assertIn("SPACED_ERROR:52", result.stdout)
                self.assertNotIn("SPACED_SUCCESS", result.stdout)
                self.assertNotIn("REBOOT_CALLED", result.stdout)
                self.assertFalse(pending)

    def test_modprobe_redirect_is_fatal_instead_of_verified(self):
        result, _ = self.run_helper("verify_modprobe_policy; echo SHOULD_NOT_CONTINUE")
        self.assertEqual(result.returncode, 42, result.stdout + result.stderr)
        self.assertNotIn("SHOULD_NOT_CONTINUE", result.stdout)

    def test_fatal_cannot_be_swallowed_by_conditional_shell_context(self):
        result, _ = self.run_helper("fatal 47 'Unsafe GRUB' || true; echo SHOULD_NOT_CONTINUE")
        self.assertEqual(result.returncode, 47)
        self.assertNotIn("SHOULD_NOT_CONTINUE", result.stdout)

    def test_audit_bypasses_privileged_setup(self):
        result, _ = self.run_helper('require_root() { exit 99; }; audit_system() { echo READ_ONLY_REPORT; }; main --audit')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("READ_ONLY_REPORT", result.stdout)

    def test_successful_recovery_can_reboot_later(self):
        result, _ = self.run_helper('REBOOT_AFTER=0; rollback_transaction 30; require_root() { :; }; reboot_system')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("REBOOT_CALLED", result.stdout)


class DriverGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("driver_gui", LIB / "spaced-nvidia-installer.py")
        cls.gui = importlib.util.module_from_spec(spec)
        gi = types.SimpleNamespace(require_version=lambda *_: None)
        repository = types.SimpleNamespace(Gtk=types.SimpleNamespace(Window=object),
                                          GLib=MagicMock(), Gdk=MagicMock())
        with patch.dict(sys.modules, {"gi": gi, "gi.repository": repository}):
            spec.loader.exec_module(cls.gui)

    def test_partial_recovery_does_not_offer_reboot(self):
        window = MagicMock()
        window.last_error_code = 52
        window.last_error = "Graphics recovery is incomplete."
        self.gui.Installer.finish_action(window, "--rollback", 52, None)
        window.show_reboot_dialog.assert_not_called()
        window.show_error.assert_called_once_with("Graphics recovery is incomplete.")
        window.progress.set_text.assert_called_once_with("Graphics recovery is incomplete")

    def test_busy_window_does_not_start_second_operation(self):
        window = MagicMock()
        window.running = True
        with patch.object(self.gui.threading, "Thread") as thread:
            self.gui.Installer.start_action(window, "--install")
        thread.assert_not_called()


if __name__ == "__main__":
    unittest.main()
