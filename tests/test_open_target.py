import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "overlays/usr/local/bin/spaced-open-target"


class OpenTargetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.home = self.root / "home"
        self.applications = self.home / ".local/share/applications"
        self.applications.mkdir(parents=True)
        self.log = self.root / "calls.log"
        for name in ("gtk-launch", "gio", "xdg-open", "notify-send"):
            fake = self.bin / name
            fake.write_text(
                "#!/bin/sh\n"
                f'printf \'%s\\n\' "{name} $*" >> "{self.log}"\n'
            )
            fake.chmod(0o755)
        self.env = os.environ | {
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "HOME": str(self.home),
        }

    def tearDown(self):
        self.tmp.cleanup()

    def invoke(self, *args):
        return subprocess.run(
            ["bash", str(SCRIPT), *args], env=self.env,
            text=True, capture_output=True, check=False,
        )

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def marker(self, name):
        path = self.root / name
        return path.exists() and path.read_text().strip() == "ran"

    def test_no_argument_prints_usage(self):
        result = self.invoke()
        self.assertEqual(result.returncode, 2)
        self.assertIn("Usage:", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_desktop_under_applications_uses_gtk_launch(self):
        desktop = self.applications / "myapp.desktop"
        desktop.write_text("[Desktop Entry]\nName=My App\nType=Application\nExec=x\n")
        self.invoke(str(desktop))
        self.assertEqual(self.calls(), ["gtk-launch myapp"])

    def test_desktop_outside_applications_uses_gio(self):
        desktop = self.root / "elsewhere/other.desktop"
        desktop.parent.mkdir()
        desktop.write_text("[Desktop Entry]\nName=Other\nType=Application\nExec=x\n")
        self.invoke(str(desktop))
        self.assertEqual(self.calls(), ["gio launch " + str(desktop)])

    def test_bare_id_known_to_gtk_launch(self):
        (self.applications / "knownapp.desktop").write_text(
            "[Desktop Entry]\nName=Known\nType=Application\nExec=x\n"
        )
        self.invoke("knownapp")
        self.assertEqual(self.calls(), ["gtk-launch knownapp"])

    def test_executable_file_runs_directly(self):
        script = self.root / "runnable.sh"
        script.write_text("#!/bin/sh\nprintf 'ran\\n' > " + str(self.root / "marker-exec") + "\n")
        script.chmod(0o755)
        self.invoke(str(script))
        self.assertTrue(self.marker("marker-exec"))
        self.assertEqual(self.calls(), [])

    def test_non_executable_shebang_script_runs_via_interpreter(self):
        script = self.root / "plain.sh"
        script.write_text("#!/bin/sh\nprintf 'ran\\n' > " + str(self.root / "marker-plain") + "\n")
        script.chmod(0o644)
        self.invoke(str(script))
        self.assertTrue(self.marker("marker-plain"))
        self.assertEqual(self.calls(), [])

    def test_plain_file_opens_with_xdg(self):
        document = self.root / "notes.txt"
        document.write_text("just text\n")
        self.invoke(str(document))
        self.assertEqual(self.calls(), ["xdg-open " + str(document)])

    def test_directory_opens_with_xdg(self):
        folder = self.root / "a-folder"
        folder.mkdir()
        self.invoke(str(folder))
        self.assertEqual(self.calls(), ["xdg-open " + str(folder)])

    def test_missing_target_notifies_and_fails(self):
        result = self.invoke("does-not-exist")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            self.calls(),
            ["notify-send Shortcut target not found does-not-exist"],
        )


if __name__ == "__main__":
    unittest.main()
