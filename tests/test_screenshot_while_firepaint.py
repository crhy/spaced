"""Issue f051: Print and Shift+Print must produce an image while fire burns.

Fire Writing holds a Compiz screen grab for the whole stroke, and Enhanced Zoom
holds one for the Shift+Super chord alone. Compiz turns that into an X pointer
and keyboard grab on its grab window (src/screen.c: pushScreenGrab), and the X
server keeps one grab at a time: another client's XGrabPointer or XGrabKeyboard
returns GrabAlreadyGrabbed. mate-screenshot selects its area with exactly such
a grab, so Shift+Print produced no image at all while fire was on screen. The
Compiz screenshot plug-in has the same rule in its own words - otherScreenGrab
Exist refuses to start a drag while another plug-in holds a grab - so the
Ctrl+Shift+drag shortcut did nothing mid-stroke either.

The shipped queues must let both grabs step aside for a keyboard shortcut, and
the profile must still reach the shortcuts while the Shift+Super chord is held:
Compiz matches a shortcut's modifiers exactly (src/event.c), so <Shift>Print
does not fire with Super down.
"""
from pathlib import Path
import importlib.util
import re
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
PROFILE = ROOT / "overlays/etc/skel/.config/compiz/compizconfig/Default.ini"
CORE_QUEUE = ROOT / "patches/compiz"
MAIN_QUEUE = ROOT / "patches/compiz-plugins-main"
EXTRA_QUEUE = ROOT / "patches/compiz-plugins-extra"
SCREENSHOT_PATCH = CORE_QUEUE / "0004-screenshot-works-over-fire-grab.patch"
FIREPAINT_PATCH = EXTRA_QUEUE / "0001-firepaint-yields-grab-to-key-shortcuts.patch"
EZOOM_PATCH = MAIN_QUEUE / "0003-ezoom-wheel-grab-yields-to-key-shortcuts.patch"
FIRE_GRAB = "firepaint"
WHEEL_GRAB = "ezoom-wheel"

spec = importlib.util.spec_from_file_location(
    "migration", ROOT / "overlays/usr/lib/spaced-linux/migrate-desktop.py")
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


def ini_values(text):
    """Every 'key = value' assignment in the Compiz profile."""
    return re.findall(r"(?m)^([a-z0-9_]+)\s*=\s*(.+?)\s*$", text)


def command_pairs(text):
    """(command, shortcut) pairs the commands plug-in will run.

    The shipped profile writes 'key = value', the migration writes 'key=value'.
    """
    commands = dict(re.findall(r"(?m)^as_command(\d+)\s*=\s*(.+?)\s*$", text))
    keys = dict(re.findall(r"(?m)^as_run_command(\d+)_key\s*=\s*(.+?)\s*$", text))
    return [(commands[n], keys[n]) for n in commands if n in keys]


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.text = PROFILE.read_text(encoding="utf-8")
        self.pairs = command_pairs(self.text)

    def test_the_screenshot_shortcuts_are_bound(self):
        self.assertIn(("mate-screenshot", "<Print>"), self.pairs)
        self.assertIn(("mate-screenshot --area", "<Shift>Print"), self.pairs)

    def test_the_shortcuts_still_reach_the_plug_in_while_the_chord_is_held(self):
        # A held Shift+Super stroke adds Super to the Print event, and Compiz
        # requires the modifier part of a shortcut to match exactly.
        self.assertIn(("mate-screenshot", "<Super>Print"), self.pairs)
        self.assertIn(("mate-screenshot --area", "<Shift><Super>Print"), self.pairs)

    def test_the_area_shot_is_the_one_that_needs_the_grab(self):
        # --area selects with XGrabPointer; the whole-desktop shot does not.
        area = [command for command, key in self.pairs
                if re.search(r"Print", key)]
        self.assertIn("mate-screenshot --area", area)

    def test_no_other_action_claims_a_print_key(self):
        expected = ["<Print>", "<Shift>Print", "<Super>Print",
                    "<Shift><Super>Print"]
        bound = [value for key, value in ini_values(self.text)
                 if key.startswith("as_run_command") and "Print" in value]
        self.assertEqual(sorted(bound), sorted(expected),
                         "a Print key is bound twice or to the wrong action")
        others = [value for key, value in ini_values(self.text)
                  if not key.startswith("as_run_command") and "Print" in value]
        self.assertEqual(others, [], "another Compiz action claims a Print key")

    def test_the_fire_and_zoom_shortcuts_are_untouched(self):
        self.assertIn("as_initiate_button = <Shift><Super>Button1", self.text)
        self.assertIn("as_clear_button = <Shift><Super>Button3", self.text)
        self.assertIn("as_zoom_in_button = <Shift><Super>Button4", self.text)
        self.assertIn("as_initiate_button = <Control><Shift>Button1", self.text)

    def test_fire_writing_and_enhanced_zoom_are_both_active(self):
        core = re.search(r"(?m)^as_active_plugins = (.+)$", self.text).group(1)
        self.assertIn("firepaint", core)
        self.assertIn("ezoom", core)
        self.assertIn("screenshot", core)
        self.assertIn("commands", core)


class PatchQueueTests(unittest.TestCase):
    def test_every_patch_targets_its_own_component(self):
        for patch, target in ((SCREENSHOT_PATCH, "plugins/screenshot.c"),
                              (FIREPAINT_PATCH, "src/firepaint/firepaint.c"),
                              (EZOOM_PATCH, "src/ezoom/ezoom.c")):
            self.assertTrue(patch.is_file(), f"missing {patch}")
            text = patch.read_text(encoding="utf-8")
            self.assertIn(f"--- a/{target}", text)
            self.assertIn(f"+++ b/{target}", text)

    def test_the_screenshot_plug_in_tolerates_the_fire_grabs(self):
        text = SCREENSHOT_PATCH.read_text(encoding="utf-8")
        self.assertIn('otherScreenGrabExist (s, "screenshot", '
                      f'"{FIRE_GRAB}", "{WHEEL_GRAB}", NULL)', text)
        # The plug-in must still refuse to start over its own grab twice over.
        self.assertIn('if (!ss->grabIndex)', text)

    def test_the_fire_grab_yields_to_a_key_and_is_taken_again(self):
        text = FIREPAINT_PATCH.read_text(encoding="utf-8")
        for needle in (f'pushScreenGrab (s, None, "{FIRE_GRAB}")',
                       "fireYieldGrab (s);", "fireTakeGrab (s);",
                       "case KeyPress:", "case KeyRelease:",
                       "if (event->type == ButtonPress)"):
            self.assertIn(needle, text)

    def test_the_zoom_grab_yields_to_a_key_as_well(self):
        text = EZOOM_PATCH.read_text(encoding="utf-8")
        for needle in ("zs->wheelGrabIndex",
                       "removeScreenGrab (s, zs->wheelGrabIndex, NULL);",
                       "if (event->type == KeyPress || event->type == KeyRelease)"):
            self.assertIn(needle, text)

    def test_the_grab_names_match_the_names_the_plug_ins_use(self):
        # A name the plug-in never takes would make the tolerance a no-op.
        self.assertIn(f'pushScreenGrab (s, None, "{FIRE_GRAB}")',
                      FIREPAINT_PATCH.read_text(encoding="utf-8"))
        self.assertIn(f'pushScreenGrab (s, None, "{WHEEL_GRAB}")',
                      (MAIN_QUEUE / "0001-ezoom-consume-smooth-scroll.patch")
                      .read_text(encoding="utf-8"))

    def test_the_earlier_fixes_are_not_reverted(self):
        # Removing the chord grab would fix screenshots and re-break #371, and
        # dropping the button rule would re-break fire writing itself.
        smooth = (MAIN_QUEUE / "0001-ezoom-consume-smooth-scroll.patch"
                  ).read_text(encoding="utf-8")
        self.assertIn(f'pushScreenGrab (s, None, "{WHEEL_GRAB}")', smooth)
        self.assertIn(f'otherScreenGrabExist (s, "{WHEEL_GRAB}", NULL)', smooth)
        button_yield = (MAIN_QUEUE / "0002-ezoom-wheel-grab-yields-to-other-buttons.patch"
                        ).read_text(encoding="utf-8")
        self.assertIn("zoomWheelButton", button_yield)
        self.assertIn("if (event->type == ButtonRelease)", button_yield)

    def test_the_extra_queue_pins_its_sources(self):
        hashes = EXTRA_QUEUE / "sources.sha256"
        self.assertTrue(hashes.is_file())
        lines = [line.split() for line in
                 hashes.read_text(encoding="utf-8").split("\n") if line.strip()]
        self.assertEqual(len(lines), 3, "expected a .dsc and two archives")
        names = " ".join(filename for _, filename in lines)
        self.assertIn(".dsc", names)
        self.assertIn(".orig.tar.", names)
        self.assertIn(".debian.tar.", names)
        for digest, filename in lines:
            self.assertEqual(len(digest), 64, filename)

    def test_the_extra_package_is_built_staged_and_published(self):
        for script in ("scripts/iso/build-compiz-plugins-extra.sh",
                       "scripts/iso/stage-compiz-plugins-extra.sh"):
            self.assertTrue((ROOT / script).is_file(), script)
        pipeline = (ROOT / "scripts/iso/build-marco-chroot.sh"
                    ).read_text(encoding="utf-8")
        self.assertIn("build-compiz-plugins-extra.sh", pipeline)
        self.assertIn("stage-compiz-plugins-extra.sh", pipeline)
        self.assertIn("stage-compiz-plugins-extra.sh",
                      (ROOT / "scripts/iso/build-local-packages.sh")
                      .read_text(encoding="utf-8"),
                      "the rebuilt package must reach the ISO")
        repo = (ROOT / "scripts/build-apt-repo.sh").read_text(encoding="utf-8")
        self.assertIn("compiz-plugins-extra_*.dsc", repo,
                      "the rebuilt package must ship with its source")

    def test_the_rebuilt_package_versions_agree_across_the_pipeline(self):
        for pair in (("scripts/iso/build-compiz-plugins-main.sh",
                      "scripts/iso/stage-compiz-plugins-main.sh"),
                     ("scripts/iso/build-compiz-plugins-extra.sh",
                      "scripts/iso/stage-compiz-plugins-extra.sh")):
            versions = set()
            for script in pair:
                match = re.search(r"(?m)^VERSION=(.+)$",
                                  (ROOT / script).read_text(encoding="utf-8"))
                self.assertIsNotNone(match, script)
                versions.add(match.group(1))
            self.assertEqual(len(versions), 1, versions)
            self.assertIn("spaced11.26", versions.pop())


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.profile = Path(self.temp.name) / "compiz/compizconfig/Default.ini"
        self.profile.parent.mkdir(parents=True)

    def write(self, text):
        self.profile.write_text(text, encoding="utf-8")

    def test_an_upgraded_account_gets_the_screenshot_shortcuts(self):
        self.write("[core]\nas_active_plugins=core;commands;\n"
                   "[commands]\nas_command0=xterm\n"
                   "as_run_command0_key=<Control><Alt>t\n")
        migration.migrate_compiz(self.profile)
        text = self.profile.read_text(encoding="utf-8")
        self.assertIn("as_run_command1_key=<Print>", text)
        self.assertIn("as_run_command2_key=<Shift>Print", text)
        self.assertIn("as_command0=xterm", text)

    def test_a_personal_print_binding_is_never_overwritten(self):
        self.write("[commands]\nas_command0=my-own-tool\n"
                   "as_run_command0_key=<Shift>PrintScreen\n")
        migration.migrate_compiz(self.profile)
        text = self.profile.read_text(encoding="utf-8")
        self.assertIn("as_command0=my-own-tool", text)
        self.assertIn("as_run_command0_key=<Shift>PrintScreen", text)

    def test_running_the_migration_twice_changes_nothing(self):
        self.write("[core]\nas_active_plugins=core;\n")
        migration.migrate_compiz(self.profile)
        first = self.profile.read_text(encoding="utf-8")
        migration.migrate_compiz(self.profile)
        self.assertEqual(first, self.profile.read_text(encoding="utf-8"))

    def test_the_shipped_profile_and_the_migration_agree(self):
        shipped = set(command_pairs(PROFILE.read_text(encoding="utf-8")))
        self.write("[core]\nas_active_plugins=core;\n")
        migration.migrate_compiz(self.profile)
        migrated = set(command_pairs(self.profile.read_text(encoding="utf-8")))
        for pair in shipped:
            if "Print" not in pair[1]:
                continue
            self.assertIn(pair, migrated,
                          "the image and the migration bind different "
                          "screenshot shortcuts")


if __name__ == "__main__":
    unittest.main()
