"""Argument, inventory and comparison checks for the issue #417 migration report.

Nothing here needs a network, root, a display, Flatpak remotes or APT indexes:
the package and Flatpak probes are stubbed in a temporary bin/, and the two
"systems" are two trees of .desktop files.
"""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "overlays/usr/local/bin/spaced-migration-report"
SHIPPED_APP_SET = ROOT / "overlays/usr/share/spaced-linux/app-set.txt"


class MigrationReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        # The machine the report runs on: the migrated Spaced system.
        self.home = self.root / "new-home"
        self.new_xdg = self.root / "new-xdg/share/applications"
        # The machine the inventory was captured from: the old desktop.
        self.old_home = self.root / "old-home"
        self.old_xdg = self.root / "old-xdg/share/applications"
        for directory in (self.home / ".local/share/applications",
                         self.new_xdg,
                         self.old_home / ".local/share/applications",
                         self.old_xdg):
            directory.mkdir(parents=True)
        self.inventory = self.root / "inventory.txt"
        self.app_set = self.root / "app-set.txt"
        self.app_set.write_text(
            "engrampa\tapt\nmintstick\tapt\npluma\tapt\nflatpak\tflatpak\n",
            encoding="utf-8",
        )
        self.write_stub("apt-cache", """
            case "$2" in
                gimp|engrampa) printf '  Candidate: 2.99\\n' ;;
                *) printf '  Candidate: (none)\\n' ;;
            esac
        """)
        self.write_stub("flatpak", """
            case "$*" in
                *com.obsproject.Studio*) exit 0 ;;
            esac
            exit 1
        """)
        self.write_stub("dpkg-query", "printf 'not-installed\\n'")

    def tearDown(self):
        self.tmp.cleanup()

    def write_stub(self, name, body):
        (self.bin / name).write_text("#!/bin/sh\n" + body, encoding="utf-8")
        (self.bin / name).chmod(0o755)

    def desktop(self, directory, name, display_name, exec_line):
        (directory / name).write_text(
            "[Desktop Entry]\n"
            f"Name={display_name}\n"
            "Type=Application\n"
            f"Exec={exec_line}\n",
            encoding="utf-8",
        )

    def old_system(self):
        user = self.old_home / ".local/share/applications"
        self.desktop(user, "gimp.desktop", "GIMP", "gimp %F")
        self.desktop(user, "mintstick.desktop", "mintstick", "mintstick")
        (user / "broken.desktop").write_text(
            "[Desktop Entry]\nName=Broken\nType=Application\n", encoding="utf-8")
        self.desktop(self.old_xdg, "obs-studio.desktop",
                     "OBS Studio", "flatpak run com.obsproject.Studio")
        self.desktop(self.old_xdg, "engrampa.desktop", "Engrampa", "engrampa %f")
        self.desktop(self.old_xdg, "plasma-locker.desktop",
                     "KDE Plasma Screen Locker", "plasma-locker")

    def new_system(self, extra=()):
        self.desktop(self.home / ".local/share/applications",
                     "mintstick.desktop", "mintstick", "mintstick")
        for name in extra:
            self.desktop(self.new_xdg, name + ".desktop", name, name)

    def invoke(self, *args, home=None, xdg="new", stdin=None, dpkg="not-installed"):
        env = os.environ | {
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "HOME": str(home if home is not None else self.home),
            "SPACED_APP_SET": str(self.app_set),
        }
        if xdg == "new":
            env["XDG_DATA_DIRS"] = str(self.new_xdg.parent)
        elif xdg == "old":
            env["XDG_DATA_DIRS"] = str(self.old_xdg.parent)
        else:
            env.pop("XDG_DATA_DIRS", None)
        if dpkg != "not-installed":
            self.write_stub("dpkg-query", "printf 'installed\\n'")
        return subprocess.run(
            ["bash", str(SCRIPT), *args], env=env, cwd=str(self.root),
            input=stdin, text=True, capture_output=True, check=False,
        )

    def inventory_lines(self):
        return self.inventory.read_text(encoding="utf-8").splitlines()

    def test_unknown_argument_prints_usage(self):
        result = self.invoke("--no-such-mode")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Usage: spaced-migration-report", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_missing_inventory_is_a_clear_message_not_a_failure(self):
        result = self.invoke()
        self.assertEqual(result.returncode, 0)
        self.assertIn("No inventory captured yet", result.stdout)
        self.assertIn("--snapshot", result.stdout)

    def test_snapshot_writes_one_line_per_desktop_entry(self):
        self.old_system()
        result = self.invoke("--snapshot", str(self.inventory),
                             home=self.old_home, xdg="old")
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = self.inventory_lines()
        self.assertEqual(len(lines), 5, lines)
        self.assertEqual([line.split("\t")[0] for line in lines],
                         ["GIMP", "mintstick", "Engrampa", "OBS Studio",
                          "KDE Plasma Screen Locker"])
        for line in lines:
            self.assertEqual(len(line.split("\t")), 3, line)
        self.assertNotIn("Broken", "\n".join(lines))

    def test_report_names_every_reason_and_reinstall_command(self):
        self.old_system()
        self.new_system()
        self.invoke("--snapshot", str(self.inventory), home=self.old_home,
                    xdg="old")
        result = self.invoke("--inventory", str(self.inventory))
        self.assertEqual(result.returncode, 0)
        self.assertIn("Spaced does not ship it", result.stdout)
        self.assertIn("Spaced ships it as engrampa but it is not installed",
                      result.stdout)
        self.assertIn("only in Flathub", result.stdout)
        self.assertIn("sudo apt install gimp", result.stdout)
        self.assertIn("flatpak install --user flathub com.obsproject.Studio",
                      result.stdout)
        self.assertIn("sudo apt install engrampa", result.stdout)
        self.assertIn("not in Devuan or Flathub: keep the .desktop out of your menu",
                      result.stdout)
        self.assertNotIn("mintstick\t", result.stdout)
        self.assertIn("Nothing was installed or queued", result.stdout)

    def test_quiet_prints_only_the_count(self):
        self.old_system()
        self.new_system()
        self.invoke("--snapshot", str(self.inventory), home=self.old_home,
                    xdg="old")
        result = self.invoke("--inventory", str(self.inventory), "--quiet")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "4")

    def test_installed_app_set_package_is_not_reported_as_lost(self):
        self.old_system()
        self.new_system()
        self.invoke("--snapshot", str(self.inventory), home=self.old_home,
                    xdg="old")
        result = self.invoke("--inventory", str(self.inventory),
                             "--quiet", dpkg="installed")
        self.assertEqual(result.stdout.strip(), "3")
        full = self.invoke("--inventory", str(self.inventory), dpkg="installed")
        self.assertNotIn("engrampa", full.stdout)

    def test_inventory_dash_reads_stdin(self):
        self.old_system()
        self.new_system()
        self.invoke("--snapshot", str(self.inventory), home=self.old_home,
                    xdg="old")
        with open(self.inventory, encoding="utf-8") as handle:
            result = self.invoke("--inventory", "-", stdin=handle.read())
        self.assertEqual(result.returncode, 0)
        self.assertIn("sudo apt install gimp", result.stdout)

    def test_snapshot_defaults_under_the_home_that_survives_home_reuse(self):
        self.old_system()
        result = self.invoke("--snapshot", home=self.old_home, xdg="old")
        self.assertEqual(result.returncode, 0, result.stderr)
        default = self.old_home / ".local/share/spaced-linux/migration-inventory.txt"
        self.assertTrue(default.is_file())
        self.assertEqual(len(default.read_text(encoding="utf-8").splitlines()), 5)

    def test_shipped_app_set_is_tagged_and_covers_the_mate_applications(self):
        lines = SHIPPED_APP_SET.read_text(encoding="utf-8").splitlines()
        self.assertIn("mintstick\tapt", lines)
        self.assertIn("engrampa\tapt", lines)
        self.assertIn("flatpak\tflatpak", lines)
        for line in lines:
            self.assertEqual(len(line.split("\t")), 2, line)


if __name__ == "__main__":
    unittest.main()
