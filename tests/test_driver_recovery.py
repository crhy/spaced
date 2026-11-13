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


def load_postboot():
    """Load the login checker with a stub gi, exactly as the shipped tests do."""
    postboot_spec = importlib.util.spec_from_file_location("postboot", LIB / "spaced-nvidia-postboot.py")
    module = importlib.util.module_from_spec(postboot_spec)
    gi = types.SimpleNamespace(require_version=lambda *_: None)
    with patch.object(sys, "path", [str(LIB), *sys.path]), patch.dict(
        sys.modules, {"gi": gi, "gi.repository": types.SimpleNamespace(Gtk=object)}
    ):
        postboot_spec.loader.exec_module(module)
    return module


postboot = load_postboot()


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

    def test_cuda_repository_and_public_key_are_restored(self):
        key = self.write("usr/share/keyrings/cuda-archive-keyring.gpg", "existing key\n")
        config.backup(self.root, self.manifest)
        key.write_text("installer key\n")
        source = self.write("etc/apt/sources.list.d/cuda-debian13-x86_64.list", "new source\n")
        config.capture(self.root, self.manifest)
        self.assertTrue(config.restore(self.root, self.manifest))
        self.assertEqual(key.read_text(), "existing key\n")
        self.assertFalse(source.exists())

    def test_disabled_legacy_cuda_repository_is_restored(self):
        config.backup(self.root, self.manifest)
        disabled = self.write(
            "etc/apt/sources.list.d/cuda-debian13-x86_64.list.spaced-legacy-disabled",
            "disabled source\n",
        )
        config.capture(self.root, self.manifest)
        self.assertTrue(config.restore(self.root, self.manifest))
        self.assertFalse(disabled.exists())


class DriverHelperTests(unittest.TestCase):
    def run_helper(self, action, failure=""):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / "run"
            run.mkdir()
            (run / "packages-before.txt").write_text("base-package\n")
            (run / "driver-versions-before.txt").write_text("")
            (run / "new-nvidia-packages.txt").write_text("nvidia-new\n")
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

    def test_working_nvidia_driver_is_kept_without_explicit_replacement(self):
        result, _ = self.run_helper(r'''
require_root() { :; }
resolve_desktop_user() { :; }
new_run() {
    RUN_DIR="$TEST_ROOT/run"
    LOG_FILE="$TEST_ROOT/install.log"
}
detect_nvidia_gpu() { printf 'NVIDIA test GPU\n'; }
working_nvidia_driver() { return 0; }
apt-get() { echo APT_MUST_NOT_RUN; }
install_system
echo SHOULD_NOT_CONTINUE
''')
        self.assertEqual(result.returncode, 25, result.stdout + result.stderr)
        self.assertIn("already running successfully", result.stdout + result.stderr)
        self.assertNotIn("APT_MUST_NOT_RUN", result.stdout)
        self.assertNotIn("SHOULD_NOT_CONTINUE", result.stdout)

    def test_replacement_requires_explicit_helper_flag(self):
        result, _ = self.run_helper(r'''
parse_args --install --replace-working-driver
printf 'MODE:%s REPLACE:%s\n' "$MODE" "$REPLACE_WORKING_DRIVER"
''')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("MODE:--install REPLACE:1", result.stdout)

    def test_successful_recovery_can_reboot_later(self):
        result, _ = self.run_helper('REBOOT_AFTER=0; rollback_transaction 30; require_root() { :; }; reboot_system')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("REBOOT_CALLED", result.stdout)

    def test_upstream_debian_alias_selects_one_guarded_package(self):
        result, _ = self.run_helper(r'''
DEBIAN_VERSION=13
nvidia-driver-assistant() {
    if [ "$1" = --list-supported-distros ]; then
        printf 'The following are the currently accepted distribution aliases:\n  debian\n  ubuntu\n'
    else
        printf '  sudo apt-get install -Vy nvidia-open\n'
    fi
}
python3() {
    if [ "$2" = recommendation ]; then printf 'nvidia-open\n'; fi
}
require_candidate() { :; }
select_driver_package
printf 'SELECTED:%s\n' "$DRIVER_PACKAGE"
''')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("SELECTED:nvidia-open", result.stdout)
        self.assertIn("--simulate --no-remove install -y nvidia-open", result.stdout)

    def test_pascal_selects_devuan_driver_even_with_nvidia_repo_enabled(self):
        result, _ = self.run_helper(r'''
DEBIAN_VERSION=13
CUDA_SOURCE_FILE="$TEST_ROOT/cuda.list"
CUDA_DISABLED_SOURCE="$TEST_ROOT/cuda.list.spaced-legacy-disabled"
printf 'deb NVIDIA\n' > "$CUDA_SOURCE_FILE"
apt-cache() {
    if [ "$1" = madison ]; then
        printf ' nvidia-driver | 610.57.04-1 | https://developer.download.nvidia.com/compute/cuda/repos/debian13/x86_64  Packages\n'
        printf ' nvidia-driver | 550.163.01-5.1 | http://deb.devuan.org/merged ceres/non-free amd64 Packages\n'
    fi
}
nvidia-driver-assistant() {
    if [ "$1" = --list-supported-distros ]; then
        printf '  debian\n'
    else
        echo ASSISTANT_RECOMMENDATION_MUST_NOT_RUN
        return 99
    fi
}
python3() {
    if [ "$2" = hardware ]; then
        printf 'Supported NVIDIA device: GeForce GTX 1080 [10de:1b80] (legacy 580.xx)\n'
    elif [ "$2" = legacy-version ]; then
        printf '550.163.01-5.1\n'
    fi
}
select_driver_package
printf 'SELECTED:%s\n' "$DRIVER_PACKAGE"
test ! -e "$CUDA_SOURCE_FILE" && printf 'SOURCE:disabled\n'
test -e "$CUDA_DISABLED_SOURCE" && printf 'LEGACY_GUARD:present\n'
''')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("SELECTED:nvidia-driver=550.163.01-5.1", result.stdout)
        self.assertIn("--simulate --no-remove install -y nvidia-driver=550.163.01-5.1", result.stdout)
        self.assertIn("SOURCE:disabled", result.stdout)
        self.assertIn("LEGACY_GUARD:present", result.stdout)
        self.assertNotIn("ASSISTANT_RECOMMENDATION_MUST_NOT_RUN", result.stdout)

    def test_driver_apt_failure_stops_before_dkms(self):
        result, _ = self.run_helper(r'''
DRIVER_PACKAGE=nvidia-open
dkms() { echo DKMS_SHOULD_NOT_RUN; }
install_driver_packages
''', "apt-get")
        self.assertEqual(result.returncode, 30, result.stdout + result.stderr)
        self.assertNotIn("DKMS_SHOULD_NOT_RUN", result.stdout)
        self.assertIn("--no-remove install -y nvidia-open", result.stdout)

    def test_manual_recovery_keeps_completed_package_record(self):
        result, _ = self.run_helper(r'''
record_new_nvidia_packages() { echo MUST_NOT_RESCAN_LATER_INSTALLS; return 99; }
rollback_transaction 30
''')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("MUST_NOT_RESCAN_LATER_INSTALLS", result.stdout)

    def test_recovery_rejects_removal_of_later_dependent_app(self):
        result, _ = self.run_helper(r'''
apt-get() {
    if [[ " $* " = *" --simulate "* ]]; then
        printf 'Remv nvidia-new [1.0]\nRemv unrelated-cuda-app [2.0]\n'
    else
        echo REAL_PURGE_MUST_NOT_RUN
    fi
}
remove_recorded_nvidia_packages nvidia-new
''')
        self.assertEqual(result.returncode, 52, result.stdout + result.stderr)
        self.assertIn("unrelated-cuda-app", result.stdout)
        self.assertNotIn("REAL_PURGE_MUST_NOT_RUN", result.stdout)


class InterruptedTransactionTests(unittest.TestCase):
    """a05-1: a rollback started in a new process must recover an interrupted install."""

    ORIGINAL_GRUB = 'GRUB_CMDLINE_LINUX_DEFAULT="quiet splash"\n'
    INSTALLER_GRUB = 'GRUB_CMDLINE_LINUX_DEFAULT="quiet splash nvidia-drm.modeset=1 modprobe.blacklist=nouveau"\n'

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.root = self.work / "root"
        self.manifest = self.work / "run" / "configuration.json"
        (self.root / "etc/default").mkdir(parents=True)
        (self.root / "etc/default/grub").write_text(self.ORIGINAL_GRUB)
        self.manifest.parent.mkdir()

    def run_config(self, *args):
        return subprocess.run([sys.executable, str(LIB / "spaced-nvidia-config.py"), *args],
                              text=True, capture_output=True)

    def test_pending_reports_an_interrupted_transaction(self):
        grub = self.root / "etc/default/grub"
        config.backup(self.root, self.manifest)
        grub.write_text(self.INSTALLER_GRUB)
        interrupted = self.run_config("pending", str(self.manifest))
        self.assertEqual(interrupted.returncode, 0, interrupted.stdout + interrupted.stderr)
        self.assertEqual(interrupted.stdout, "")
        config.capture(self.root, self.manifest)
        completed = self.run_config("pending", str(self.manifest))
        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        absent = self.run_config("pending", str(self.work / "no-such-manifest.json"))
        self.assertEqual(absent.returncode, 1, absent.stdout + absent.stderr)
        broken = self.work / "broken.json"
        broken.write_text("{ not json")
        invalid = self.run_config("pending", str(broken))
        self.assertEqual(invalid.returncode, 52, invalid.stdout + invalid.stderr)
        self.assertIn("Graphics configuration recovery:", invalid.stdout)

    def test_interrupted_transaction_recovers_after_recording_its_partial_result(self):
        grub = self.root / "etc/default/grub"
        config.backup(self.root, self.manifest)
        grub.write_text(self.INSTALLER_GRUB)
        policy = self.root / "etc/modprobe.d/zz-spaced-nvidia.conf"
        policy.parent.mkdir(parents=True)
        policy.write_text("blacklist nouveau\n")
        self.assertEqual(self.run_config("restore", str(self.manifest), "--root", str(self.root)).returncode, 52)
        config.capture(self.root, self.manifest)
        self.assertTrue(config.restore(self.root, self.manifest))
        self.assertEqual(grub.read_text(), self.ORIGINAL_GRUB)
        self.assertFalse(policy.exists())

    def run_interrupted_rollback(self):
        """Run rollback_transaction with no "after" record and TRANSACTION_ACTIVE=0."""
        config.backup(self.root, self.manifest)
        (self.root / "etc/default/grub").write_text(self.INSTALLER_GRUB)
        policy = self.root / "etc/modprobe.d/zz-spaced-nvidia.conf"
        policy.parent.mkdir(parents=True, exist_ok=True)
        policy.write_text("blacklist nouveau\n")
        (self.manifest.parent / "packages-before.txt").write_text("base-package\n")
        (self.manifest.parent / "driver-versions-before.txt").write_text("")
        (self.work / "current-run").write_text(f"{self.manifest.parent}\n")
        helper = self.work / "helper"
        source = (LIB / "spaced-nvidia-helper").read_text()
        source = source.replace("/sbin/reboot", "mock_reboot")
        source = source.replace("/usr/lib/spaced-linux/spaced-nvidia-config.py",
                                str(LIB / "spaced-nvidia-config.py"))
        helper.write_text(source)
        script = self.work / "run.sh"
        script.write_text(r'''
dpkg() { printf 'amd64\n'; }
source "$TEST_HELPER"
RUN_DIR=""
PENDING_FILE="$TEST_ROOT/pending"
RECOVERED_FILE="$TEST_ROOT/recovered"
CURRENT_RUN_FILE="$TEST_ROOT/current-run"
KERNEL=test-kernel
TRANSACTION_ACTIVE=0
REBOOT_AFTER=0
dpkg() { printf 'CALL:dpkg %s\n' "$*"; }
dpkg-query() { printf 'ii\tnvidia-new\n'; }
apt-get() { printf 'CALL:apt-get %s\n' "$*"; }
update-initramfs() { printf 'CALL:update-initramfs %s\n' "$*"; }
update-grub() { printf 'CALL:update-grub %s\n' "$*"; }
update-glx() { printf 'CALL:update-glx %s\n' "$*"; }
dconf() { printf 'CALL:dconf %s\n' "$*"; }
restore_configuration() {
    printf 'CALL:restore_configuration\n'
    python3 "$TEST_CONFIG" restore "$RUN_DIR/configuration.json" --root "$TEST_ROOT/root"
}
record_configuration_changes() {
    printf 'CALL:record_configuration_changes\n'
    python3 "$TEST_CONFIG" capture "$RUN_DIR/configuration.json" --root "$TEST_ROOT/root"
}
rollback_transaction 30
''')
        env = os.environ.copy()
        env.update(TEST_ROOT=str(self.work), TEST_HELPER=str(helper),
                   TEST_CONFIG=str(LIB / "spaced-nvidia-config.py"))
        result = subprocess.run(["bash", str(script)], env=env, text=True, capture_output=True)
        return result, policy

    def test_rollback_in_a_new_process_recovers_an_interrupted_install(self):
        result, policy = self.run_interrupted_rollback()
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        self.assertIn("The previous driver installation was interrupted", output)
        self.assertIn("CALL:record_configuration_changes", output)
        self.assertIn("CALL:restore_configuration", output)
        self.assertIn("SPACED_SUCCESS:restored", output)
        self.assertEqual((self.root / "etc/default/grub").read_text(), self.ORIGINAL_GRUB)
        self.assertFalse(policy.exists())

    def test_pending_check_precedes_the_first_recovery_step(self):
        source = (LIB / "spaced-nvidia-helper").read_text()
        body = source.split("rollback_transaction() {", 1)[1].split("\n}", 1)[0]
        first_step = body.index('rollback_step "clear previous recovery verification"')
        check = body.index("spaced-nvidia-config.py pending")
        self.assertLess(check, first_step)
        self.assertIn("was_active=1", body[:first_step])


class DriverGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("driver_gui", LIB / "spaced-nvidia-installer.py")
        cls.gui = importlib.util.module_from_spec(spec)
        gi = types.SimpleNamespace(require_version=lambda *_: None)
        repository = types.SimpleNamespace(Gtk=types.SimpleNamespace(Window=object),
                                          GLib=MagicMock(), Gdk=MagicMock())
        with patch.object(sys, "path", [str(LIB), *sys.path]), patch.dict(sys.modules, {"gi": gi, "gi.repository": repository}):
            spec.loader.exec_module(cls.gui)

    def test_partial_recovery_does_not_offer_reboot(self):
        window = MagicMock()
        window.last_error_code = 52
        window.last_error = "Graphics recovery is incomplete."
        self.gui.Installer.finish_action(window, "--rollback", 52, None)
        window.show_reboot_dialog.assert_not_called()
        window.show_error.assert_called_once_with("Graphics recovery is incomplete.")
        window.progress.set_text.assert_called_once_with("Graphics recovery is incomplete")

    def test_helper_error_lines_reach_the_copied_log(self):
        window = MagicMock()
        line = "SPACED_ERROR:52:Graphics recovery is incomplete. Repair the failed steps before rebooting."
        self.assertFalse(self.gui.Installer.process_line(window, line))
        self.assertEqual(window.last_error_code, 52)
        self.assertEqual(window.last_error, "Graphics recovery is incomplete. Repair the failed steps before rebooting.")
        window.append_log.assert_called_once_with(
            "ERROR: Graphics recovery is incomplete. Repair the failed steps before rebooting."
        )

    def test_busy_window_does_not_start_second_operation(self):
        window = MagicMock()
        window.running = True
        with patch.object(self.gui.threading, "Thread") as thread:
            self.gui.Installer.start_action(window, "--install")
        thread.assert_not_called()

    def test_gui_only_passes_replacement_flag_for_working_driver(self):
        for working, expected in ((False, False), (True, True)):
            with self.subTest(working=working):
                window = MagicMock()
                window.user = "tester"
                window.working_nvidia = working
                process = MagicMock()
                process.stdout = []
                process.wait.return_value = 0
                with patch.object(self.gui.subprocess, "Popen", return_value=process) as popen:
                    self.gui.Installer.run_action(window, "--install")
                command = popen.call_args.args[0]
                self.assertEqual("--replace-working-driver" in command, expected)


class PostbootProbeTimeoutTests(unittest.TestCase):
    """a05-5: the repeated login probes must stay short and bounded."""

    def test_cheap_probes_use_the_short_timeout(self):
        seen = {}

        def fake_run(command, timeout=postboot.FULL_TIMEOUT):
            seen.setdefault(command[0], []).append(timeout)
            return 1, "", "unavailable"

        with patch.object(postboot, "run", side_effect=fake_run):
            postboot.collect_checks(postboot.QUICK_TIMEOUT)
        self.assertEqual(seen["pgrep"], [postboot.QUICK_TIMEOUT] * 3)
        self.assertEqual(seen["wmctrl"], [postboot.QUICK_TIMEOUT])
        self.assertEqual(seen["sh"], [postboot.QUICK_TIMEOUT])
        self.assertEqual(seen["glxinfo"], [postboot.FULL_TIMEOUT])
        self.assertEqual(seen["env"], [postboot.FULL_TIMEOUT])
        self.assertEqual(seen["nvidia-smi"], [postboot.FULL_TIMEOUT])

    def test_transient_failures_stop_at_the_absolute_deadline(self):
        class FakeTime:
            def __init__(self):
                self.now = 0.0

            def monotonic(self):
                return self.now

            def sleep(self, seconds):
                self.now += seconds

        clock = FakeTime()
        rounds = []

        def failing_round(quick_timeout=None):
            rounds.append(quick_timeout)
            clock.now += 10  # a half-broken desktop burns seconds on every probe set
            return (
                ["Compiz is not the active window manager.", "MATE panel is not running."],
                "startup details",
            )

        with patch.object(postboot, "collect_checks", side_effect=failing_round), patch.object(postboot, "time", clock):
            failures, details = postboot.wait_for_session()
        self.assertLess(len(rounds), 45)
        self.assertLessEqual(len(rounds), postboot.SESSION_DEADLINE // 10 + 2)
        self.assertLessEqual(clock.now, postboot.SESSION_DEADLINE + 10)
        self.assertEqual(set(rounds), {postboot.QUICK_TIMEOUT})
        self.assertEqual(failures, ["Compiz is not the active window manager.", "MATE panel is not running."])
        self.assertEqual(details, "startup details")

    def test_permanent_failure_returns_without_retrying(self):
        rounds = []

        def failing_round(quick_timeout=None):
            rounds.append(quick_timeout)
            return ["The core nvidia module is not loaded."], "startup details"

        with patch.object(postboot, "collect_checks", side_effect=failing_round), patch.object(postboot, "time") as clock:
            failures, _ = postboot.wait_for_session()
        self.assertEqual(len(rounds), 1)
        clock.sleep.assert_not_called()
        self.assertEqual(failures, ["The core nvidia module is not loaded."])


class PostbootLoginCostTests(unittest.TestCase):
    """a02-7: a login with no pending driver install must not touch GTK."""

    def run_postboot(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        work = Path(temp.name)
        pending = work / "state" / "reboot-required"
        (work / "gi").mkdir()
        (work / "gi" / "__init__.py").write_text("raise ImportError('GTK must not be imported at login')\n")
        (work / "spaced_nvidia_state.py").write_text(
            "from pathlib import Path\n\n"
            f"PENDING = Path({str(pending)!r})\n\n"
            "def ack_path(pending=PENDING):\n    return pending.with_name('acknowledged')\n\n"
            "def awaiting_reboot(pending=PENDING):\n    return False\n\n"
            "def marker_id(pending=PENDING):\n    return 'testmarker'\n"
        )
        script = work / "spaced-nvidia-postboot.py"
        script.write_text((LIB / "spaced-nvidia-postboot.py").read_text(encoding="utf-8"))
        env = os.environ.copy()
        env["PYTHONPATH"] = str(work)
        env["HOME"] = str(work / "home")
        env.pop("DISPLAY", None)
        return subprocess.run([sys.executable, str(script)], env=env, cwd=str(work),
                              text=True, capture_output=True, timeout=60)

    def test_login_without_a_pending_install_never_imports_gtk(self):
        result = self.run_postboot()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")

    def test_gtk_is_still_loaded_when_a_dialog_is_needed(self):
        gi = MagicMock()
        repository = MagicMock()
        self.assertFalse(hasattr(postboot, "Gtk"))
        with patch.dict(sys.modules, {"gi": gi, "gi.repository": repository}):
            gtk = postboot.load_gtk()
        gi.require_version.assert_called_once_with("Gtk", "3.0")
        self.assertIs(gtk, repository.Gtk)


class PostbootRecoveryResultTests(unittest.TestCase):
    """a05-2 / a05-9: the recovery request must report its own result."""

    def run_recovery(self, returncode, stdout):
        result = MagicMock(returncode=returncode, stdout=stdout)
        with patch.object(postboot.subprocess, "run", return_value=result) as run, \
                patch.object(postboot, "show_recovery_error") as shown:
            postboot.run_recovery("tester")
        return run, shown

    def test_incomplete_recovery_shows_the_helper_error(self):
        run, shown = self.run_recovery(
            52,
            "SPACED_STATUS:Restoring the saved graphics configuration\n"
            "SPACED_ERROR:52:Graphics recovery is incomplete. Repair the failed steps before rebooting.\n",
        )
        self.assertEqual(
            run.call_args.args[0],
            ["pkexec", postboot.HELPER, "--rollback", "--reboot-after", "--desktop-user", "tester"],
        )
        shown.assert_called_once_with(
            "Graphics recovery is incomplete. Repair the failed steps before rebooting."
        )

    def test_dismissed_authentication_shows_a_status_message(self):
        _, shown = self.run_recovery(126, "pkexec: Authentication failed\n")
        self.assertEqual(shown.call_count, 1)
        self.assertIn("126", shown.call_args.args[0])

    def test_successful_recovery_shows_no_error(self):
        _, shown = self.run_recovery(0, "SPACED_SUCCESS:restored\n")
        shown.assert_not_called()

    def show_failure_with(self, response, pending, repository):
        repository.Gtk.MessageDialog.return_value.run.return_value = response
        with patch.dict(sys.modules, {"gi": MagicMock(), "gi.repository": repository}), \
                patch.object(postboot, "PENDING", pending), \
                patch.object(postboot, "run_recovery") as recovery:
            postboot.show_failure(["Nouveau is still loaded after the NVIDIA reboot."], "startup details")
        return recovery

    def test_keep_running_acknowledges_the_failed_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            (work / "home").mkdir()
            pending = work / "reboot-required"
            pending.write_text("boot_id=test-boot\n")
            repository = MagicMock()
            with patch.dict(os.environ, {"HOME": str(work / "home")}):
                recovery = self.show_failure_with(repository.Gtk.ResponseType.CANCEL, pending, repository)
                acknowledgement = postboot.ack_path(pending)
                self.assertTrue(acknowledgement.is_file())
                self.assertEqual(acknowledgement.read_text(encoding="utf-8"), "startup details\n")
                log = work / "home/.cache/spaced-nvidia-installer" / f"failed-{postboot.marker_id(pending)}.log"
                self.assertEqual(log.read_text(encoding="utf-8"), "startup details\n")
            recovery.assert_not_called()

    def test_restore_button_runs_the_helper_without_acknowledging(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            (work / "home").mkdir()
            pending = work / "reboot-required"
            pending.write_text("boot_id=test-boot\n")
            repository = MagicMock()
            with patch.dict(os.environ, {"HOME": str(work / "home")}), \
                    patch.object(postboot.pwd, "getpwuid", return_value=MagicMock(pw_name="tester")):
                recovery = self.show_failure_with(repository.Gtk.ResponseType.OK, pending, repository)
                self.assertFalse(postboot.ack_path(pending).exists())
            recovery.assert_called_once_with("tester")


if __name__ == "__main__":
    unittest.main()
