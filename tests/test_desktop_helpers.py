"""Desktop helper regressions: fake commands, throwaway HOME, no display."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "overlays/usr/local/bin"


class FakeCommandTests(unittest.TestCase):
    """Runs a shipped helper with only the commands listed here on PATH."""

    # Real utilities the helper needs, resolved from this host and symlinked
    # into a private directory so no host application can shadow a fake.
    system_commands = ()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)
        self.fakebin = self.state / "bin"
        self.fakebin.mkdir()
        self.systembin = self.state / "system-bin"
        self.systembin.mkdir()
        for name in self.system_commands:
            real = shutil.which(name)
            self.assertIsNotNone(real, f"{name} is needed to run the helper")
            os.symlink(real, self.systembin / name)
        self.home = self.state / "home"
        (self.home / ".config").mkdir(parents=True)
        self.log = self.state / "calls.log"
        self.env = dict(
            os.environ,
            HOME=str(self.home),
            XDG_CONFIG_HOME=str(self.home / ".config"),
            TEST_STATE=str(self.state),
            PATH=f"{self.fakebin}:{self.systembin}",
        )

    def command(self, name, body):
        executable = self.fakebin / name
        executable.write_text(f"#!/bin/bash\n{body}\n")
        executable.chmod(0o755)

    def log_first(self, name):
        """Log every call to <name> before the fake does anything else."""
        return (f"printf '%s %s\\n' '{name}' \"$*\" >> \"$TEST_STATE/calls.log\"")

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def run_helper(self, name, args=()):
        return subprocess.run(
            [str(BIN / name), *args], env=self.env,
            capture_output=True, text=True, timeout=30,
        )


class HotkeyMuteCalcTests(FakeCommandTests):
    """Ctrl+Alt+C must never leave the machine muted when there is no Calc."""

    system_commands = ("awk",)

    def setUp(self):
        super().setUp()
        self.command("pactl", "\n".join([
            self.log_first("pactl"),
            'case "$1" in',
            "  list) printf '1\\talsa_output.pci-0000_00_1f.3.analog-stereo\\n' ;;",
            "  get-sink-mute) printf 'Sink 1 (alsa_output) is muted: no\\n' ;;",
            "  set-sink-mute) : ;;",
            "esac",
            "exit 0",
        ]))
        self.command("amixer", self.log_first("amixer") + "\nexit 0")
        self.command("notify-send", self.log_first("notify-send") + "\nexit 0")
        self.command("zenity", self.log_first("zenity") + "\nexit 0")

    def audio_calls(self):
        return [call for call in self.calls() if call.split()[0] in ("pactl", "amixer")]

    def test_missing_spreadsheet_never_mutes(self):
        # No libreoffice on PATH and the Flatpak is not installed.
        self.command("flatpak", self.log_first("flatpak") + "\nexit 1")
        result = self.run_helper("spaced-hotkey-action", ["mute-calc"])
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.audio_calls(), [])
        self.assertEqual(
            self.calls()[-1:],
            ["notify-send Shortcut application is not installed LibreOffice Calc"],
        )

    def test_installed_libreoffice_mutes_and_starts_calc(self):
        self.command("libreoffice", self.log_first("libreoffice") + "\nexit 0")
        result = self.run_helper("spaced-hotkey-action", ["mute-calc"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.calls(),
            ["pactl list short sinks", "pactl set-sink-mute 1 1", "libreoffice --calc"],
        )

    def test_flatpak_calc_mutes_and_starts(self):
        self.command("flatpak", "\n".join([
            self.log_first("flatpak"),
            "case \"$1\" in",
            "  info) exit 0 ;;",
            "  run) exit 0 ;;",
            "esac",
            "exit 1",
        ]))
        result = self.run_helper("spaced-hotkey-action", ["mute-calc"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("pactl set-sink-mute 1 1", self.calls())
        self.assertEqual(
            self.calls()[-1], "flatpak run org.libreoffice.LibreOffice --calc")
        self.assertLess(self.calls().index("pactl set-sink-mute 1 1"),
                        len(self.calls()) - 1)


class GraphicsReportProcessCheckTests(FakeCommandTests):
    """spaced-graphics-report must answer, not fail, when no session runs."""

    system_commands = ("timeout", "grep", "tail", "head")

    report_commands = (
        "uname", "cat", "lspci", "lsusb", "lsmod", "glxinfo", "xrandr", "xset",
        "xdpyinfo", "xrdb", "xprop", "gsettings", "dpkg-query", "mokutil",
        "nvidia-smi", "env", "dkms", "dmesg",
    )

    def setUp(self):
        super().setUp()
        for name in self.report_commands:
            self.command(name, "exit 0")

    def report_section(self, ps_body):
        self.command("ps", ps_body)
        result = self.run_helper("spaced-graphics-report")
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        headers = [index for index, line in enumerate(lines) if line.startswith("--- ps -C ")]
        self.assertEqual(len(headers), 1, "the session process check section is missing")
        body = []
        for line in lines[headers[0] + 1:]:
            if line.startswith("--- "):
                break
            body.append(line)
        return "\n".join(body).strip()

    def test_no_matching_processes_is_reported_as_an_answer(self):
        # ps exits 1 with no rows when none of the listed names run.
        self.assertEqual(
            self.report_section("exit 1"),
            "No Spaced session processes are running.",
        )

    def test_running_processes_are_still_listed(self):
        section = self.report_section(
            "printf '   PID  PPID ELAPSED STAT COMMAND\\n'\n"
            "printf '  1234  1200      42 S    compiz\\n'\n"
            "exit 0"
        )
        self.assertIn("compiz", section)
        self.assertNotIn("No Spaced session processes", section)

    def test_ps_error_output_is_still_a_failed_check(self):
        section = self.report_section(
            "printf 'ps: this build does not support -C\\n'\nexit 1")
        self.assertIn("ps: this build does not support -C", section)
        self.assertIn("Check unavailable (status 1).", section)
        self.assertNotIn("No Spaced session processes", section)

    def test_other_ps_status_is_still_a_failed_check(self):
        section = self.report_section("exit 2")
        self.assertEqual(section, "Check unavailable (status 2).")


if __name__ == "__main__":
    unittest.main()
