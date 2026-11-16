"""Compiz screenshots must still work while fire painting holds a screen grab.

Guards the patch queue and the seeded profile only; nothing here needs a
running desktop.
"""
import configparser
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCH_DIR = ROOT / "patches/compiz"
BUILD_SCRIPT = ROOT / "scripts/iso/build-compiz.sh"
PROFILE = ROOT / "overlays/etc/skel/.config/compiz/compizconfig/Default.ini"


def patch_paths(patch_text):
    """Every file a patch touches, from its --- a/ and +++ b/ headers."""
    return sorted(set(re.findall(r"^[-+]{3} [ab]/(\S+)$", patch_text, re.M)))


class CompizScreenshotWhileFireTests(unittest.TestCase):
    def setUp(self):
        patches = sorted(PATCH_DIR.glob("0004-*.patch"))
        self.assertTrue(patches, "no 0004 Compiz patch exists")
        self.patch_file = patches[0]
        self.patch_text = self.patch_file.read_text(encoding="utf-8")

    def test_fire_grab_patch_exists_and_is_the_only_one(self):
        self.assertEqual(len(list(PATCH_DIR.glob("0004-*.patch"))), 1,
                         "the Compiz queue has more than one 0004 patch")
        self.assertEqual(len(list(PATCH_DIR.glob("*.patch"))), 4,
                         "the Compiz patch queue is not four patches")

    def test_patch_only_touches_the_screenshot_plugin(self):
        # The fire fix must stay inside the screenshot plugin: no theme, CSS
        # or colour file belongs in this change.
        self.assertEqual(patch_paths(self.patch_text),
                         ["plugins/screenshot.c"],
                         "the fire grab patch touches more than the screenshot plugin")

    def test_patch_lets_firepaint_hold_a_grab_during_a_capture(self):
        self.assertIn("-\tif (otherScreenGrabExist (s, \"screenshot\", NULL))",
                      self.patch_text,
                      "the patch no longer removes the blanket grab refusal")
        self.assertIn("+\tif (otherScreenGrabExist (s, \"screenshot\", \"firepaint\", NULL))",
                      self.patch_text,
                      "the screenshot plugin does not accept a firepaint grab")

    def test_patch_hunk_line_counts_are_valid(self):
        hunk_header = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
        lines = self.patch_text.splitlines()
        hunks = 0
        index = 0
        while index < len(lines):
            match = hunk_header.match(lines[index])
            if not match:
                index += 1
                continue
            hunks += 1
            expected_old = int(match.group(2) if match.group(2) is not None else 1)
            expected_new = int(match.group(4) if match.group(4) is not None else 1)
            actual_old = actual_new = 0
            index += 1
            while index < len(lines):
                line = lines[index]
                if line.startswith("@@ ") or line.startswith("--- "):
                    break
                if (actual_old, actual_new) == (expected_old, expected_new):
                    break
                self.assertTrue(line.startswith((" ", "+", "-", "\\")),
                                f"{self.patch_file.name}: malformed hunk line {index + 1}")
                if line.startswith((" ", "-")):
                    actual_old += 1
                if line.startswith((" ", "+")):
                    actual_new += 1
                index += 1
        self.assertEqual(hunks, 1, "the fire grab patch is not one hunk")

    def test_source_archives_stay_pinned_and_the_patch_is_not_one(self):
        entries = PATCH_DIR / "sources.sha256"
        tokens = entries.read_text(encoding="utf-8").split()
        self.assertEqual(len(tokens), 6,
                         "the Compiz source archives are not pinned by SHA-256")
        names = tokens[1::2]
        self.assertTrue(all(name.endswith((".dsc", ".tar.xz")) for name in names),
                        "a Compiz patch is listed as a source archive")
        self.assertFalse(any(name.endswith(".patch") for name in names))
        build = BUILD_SCRIPT.read_text(encoding="utf-8")
        self.assertIn('"$PATCHES/sources.sha256"', build,
                      "build-compiz.sh does not read the pinned archive list")
        self.assertIn("while read -r digest filename", build,
                      "build-compiz.sh does not check every pinned archive")
        self.assertIn("sha256sum --check", build,
                      "build-compiz.sh does not verify archive digests")

    def test_build_script_applies_the_new_patch(self):
        build = BUILD_SCRIPT.read_text(encoding="utf-8")
        self.assertIn('PATCHES="$ROOT/patches/compiz"', build,
                      "build-compiz.sh does not use the tracked patch queue")
        self.assertIn('for patch_file in "$PATCHES"/*.patch', build,
                      "build-compiz.sh does not apply every queued patch")
        self.assertIn('>> "$source_dir/debian/patches/series"', build,
                      "build-compiz.sh does not queue the patch for dpkg-source")

    def test_screenshot_and_fire_bindings_are_intact(self):
        self.assertTrue(PROFILE.is_file(), "the seeded Compiz profile is missing")
        parser = configparser.ConfigParser(interpolation=None)
        parser.read_string(PROFILE.read_text(encoding="utf-8"))
        self.assertIn("firepaint", parser["core"]["as_active_plugins"].split(";"),
                      "fire painting is not active in the seeded profile")
        self.assertEqual(parser["screenshot"]["as_initiate_button"],
                         "<Control><Shift>Button1",
                         "the Compiz screenshot gesture lost its binding")
        self.assertEqual(parser["commands"]["as_command0"], "mate-screenshot --area",
                         "the MATE screenshot command changed")
        self.assertEqual(parser["commands"]["as_run_command0_key"], "<Shift>Print",
                         "Shift+Print no longer takes a screenshot")
        self.assertNotIn("as_initiate_button", parser["firepaint"],
                         "the profile now overrides the fire drawing gesture")

    def test_the_queue_applies_to_the_extracted_source(self):
        source = ROOT / "build/compiz-0.8.18"
        if not source.is_dir():
            self.skipTest("the extracted Compiz source is not present")
        if shutil.which("patch") is None:
            self.skipTest("patch is not installed")
        patches = sorted(PATCH_DIR.glob("*.patch"))
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            for patch_file in patches:
                for rel in patch_paths(patch_file.read_text(encoding="utf-8")):
                    target = work / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source / rel, target)
            for patch_file in patches:
                with open(patch_file, "rb") as handle:
                    result = subprocess.run(["patch", "-p1"],
                                            cwd=work, stdin=handle,
                                            capture_output=True)
                self.assertEqual(result.returncode, 0,
                                 f"{patch_file.name}: {result.stdout.decode()}"
                                 f"{result.stderr.decode()}")

    def test_the_fire_patch_is_the_only_change_to_the_screenshot_plugin(self):
        # 0003 already rewrites the filename code; 0004 must not undo it.
        source = ROOT / "build/compiz-0.8.18"
        if not source.is_dir():
            self.skipTest("the extracted Compiz source is not present")
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            (work / "plugins").mkdir()
            shutil.copyfile(source / "plugins/screenshot.c",
                            work / "plugins/screenshot.c")
            for patch_file in sorted(PATCH_DIR.glob("000[34]-*.patch")):
                with open(patch_file, "rb") as handle:
                    result = subprocess.run(["patch", "-p1"],
                                            cwd=work, stdin=handle,
                                            capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr.decode())
            patched = (work / "plugins/screenshot.c").read_text(encoding="utf-8")
        self.assertIn("shotGetFilename", patched, "the timestamped filenames are lost")
        self.assertIn('"screenshot-%s-%d.png"', patched, "the collision suffix is lost")
        self.assertIn('otherScreenGrabExist (s, "screenshot", "firepaint", NULL)',
                      patched, "the screenshot plugin still refuses a fire grab")


if __name__ == "__main__":
    unittest.main()
