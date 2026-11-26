import os
import shutil
import time
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "overlays/usr/local/bin/spaced-wine-run"
OVERLAYS = Path(__file__).resolve().parents[1] / "overlays"
ASSOCIATION = "application/x-ms-dos-executable=spaced-wine-run.desktop"


class WineLauncherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.no_wine_bin = self.root / "no-wine-bin"
        self.no_wine_bin.mkdir()
        self.tools = self.root / "tools"
        self.tools.mkdir()
        self.home = self.root / "home"
        self.data = self.root / "data"
        self.state = self.root / "state"
        self.log = self.root / "calls.log"
        self.bash = shutil.which("bash")
        for name in ("wine", "wine64", "wineboot", "zenity", "flatpak"):
            self.write_fake(self.bin, name)
        for name in ("zenity", "flatpak"):
            self.write_fake(self.no_wine_bin, name)
        # A PATH with no /usr/bin, so the no-Wine case cannot borrow the Wine
        # that happens to be installed on the machine running the test.
        for name in ("basename", "date", "grep", "mkdir", "mv", "sed", "tee"):
            target = shutil.which(name)
            if target:
                (self.tools / name).symlink_to(target)
        self.env = os.environ | {
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "HOME": str(self.home),
            "XDG_DATA_HOME": str(self.data),
            "XDG_STATE_HOME": str(self.state),
        }
        self.without_wine = self.env | {"PATH": f"{self.no_wine_bin}:{self.tools}"}

    def tearDown(self):
        self.tmp.cleanup()

    def write_fake(self, directory, name):
        fake = directory / name
        fake.write_text(
            "#!/bin/sh\n"
            f'printf \'%s %s WINEPREFIX=%s\\n\' "{name}" "$*" '
            f'"${{WINEPREFIX:-unset}}" >> "{self.log}"\n'
            f'printf \'%s ran\\n\' "$1"\n'
        )
        fake.chmod(0o755)

    def invoke(self, *args, env=None):
        return subprocess.run(
            [self.bash, str(SCRIPT), *args],
            env=env or self.env, text=True, capture_output=True, check=False,
        )

    def app(self, name="Some App.exe"):
        path = self.root / name
        path.write_text("MZ fake executable\n")
        return path

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def wait_for_call(self, fragment, timeout=5.0):
        while timeout > 0:
            if any(fragment in line for line in self.calls()):
                return True
            time.sleep(0.02)
            timeout -= 0.02
        return False

    def prefixes(self):
        root = self.data / "wine-prefixes"
        return sorted(path.name for path in root.iterdir()) if root.is_dir() else []

    def test_no_argument_prints_usage(self):
        result = self.invoke()
        self.assertEqual(result.returncode, 2)
        self.assertIn("Usage: spaced-wine-run", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_missing_wine_runs_nothing_and_fails(self):
        result = self.invoke(str(self.app()), env=self.without_wine)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("install Wine first", result.stderr)
        self.assertTrue(any(line.startswith("zenity") for line in self.calls()))
        self.assertFalse(any(line.startswith("wine") for line in self.calls()))
        self.assertEqual(self.prefixes(), [])
        self.assertFalse((self.state / "spaced-wine").exists())

    def test_missing_wine_offers_wine_in_spaced_bazaar(self):
        self.invoke(str(self.app()), env=self.without_wine)
        self.assertTrue(self.wait_for_call("appstream://org.winehq.Wine"))

    def test_first_run_creates_prefix_and_boots_it(self):
        app = self.app()
        result = self.invoke(str(app), "doc", "--verbose")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(self.calls()), 2)
        self.assertTrue(self.calls()[0].startswith("wineboot -i "))
        wine_line = self.calls()[1]
        self.assertTrue(wine_line.startswith(f"wine {app} "))
        self.assertIn("doc --verbose", wine_line)
        prefix = self.data / "wine-prefixes" / "Some_App.exe"
        self.assertTrue(prefix.is_dir())
        self.assertIn(f"WINEPREFIX={prefix}", self.calls()[0])
        self.assertIn(f"WINEPREFIX={prefix}", wine_line)

    def test_second_run_does_not_boot_the_prefix_again(self):
        app = self.app()
        self.invoke(str(app))
        self.invoke(str(app))
        self.assertEqual(
            len([line for line in self.calls() if line.startswith("wineboot")]), 1
        )

    def test_two_apps_get_two_prefixes(self):
        self.invoke(str(self.app("First.exe")))
        self.invoke(str(self.app("Second.exe")))
        self.assertEqual(self.prefixes(), ["First.exe", "Second.exe"])
        self.assertEqual(
            len({line.split()[-1] for line in self.calls() if line.startswith("wine ")}),
            2,
        )

    def test_output_is_logged_under_state_home(self):
        app = self.app("Logged.exe")
        result = self.invoke(str(app))
        log_file = self.state / "spaced-wine" / "Logged.exe.log"
        self.assertTrue(log_file.is_file())
        self.assertIn(str(log_file), result.stderr)
        self.assertIn("Logged.exe ran", log_file.read_text())

    def test_mime_opt_in_round_trip_keeps_other_lines(self):
        mimeapps = self.home / ".config/mimeapps.list"
        mimeapps.parent.mkdir(parents=True)
        mimeapps.write_text(
            "[Default Applications]\ntext/plain=pluma.desktop\n\n"
            "[Added Associations]\ntext/plain=pluma.desktop;\n"
        )
        self.assertEqual(self.invoke("--enable-mime").returncode, 0)
        self.assertIn(ASSOCIATION, mimeapps.read_text())
        self.assertEqual(self.invoke("--disable-mime").returncode, 0)
        self.assertNotIn(ASSOCIATION, mimeapps.read_text())
        self.assertEqual(
            mimeapps.read_text(),
            "[Default Applications]\ntext/plain=pluma.desktop\n\n"
            "[Added Associations]\ntext/plain=pluma.desktop;\n",
        )

    def test_enable_mime_creates_the_user_file_with_a_header(self):
        self.assertEqual(self.invoke("--enable-mime").returncode, 0)
        mimeapps = self.home / ".config/mimeapps.list"
        self.assertEqual(
            mimeapps.read_text(), f"[Default Applications]\n{ASSOCIATION}\n"
        )

    def test_disable_mime_without_the_user_file_changes_nothing(self):
        result = self.invoke("--disable-mime")
        self.assertEqual(result.returncode, 0)
        self.assertFalse((self.home / ".config/mimeapps.list").exists())

    def test_no_recipe_or_download_is_ever_run(self):
        self.invoke(str(self.app()))
        self.invoke(str(self.app()), env=self.without_wine)
        for line in self.calls():
            for forbidden in ("winetricks", "curl", "wget"):
                self.assertNotIn(forbidden, line)

    def test_shipped_mime_tables_never_associate_windows_executables(self):
        for path in (
            OVERLAYS / "usr/share/applications/mimeapps.list",
            OVERLAYS / "etc/skel/.config/mimeapps.list",
        ):
            self.assertNotIn("application/x-ms-dos-executable", path.read_text())


if __name__ == "__main__":
    unittest.main()
