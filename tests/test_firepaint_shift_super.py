"""Issue f050: Shift+Super+left-drag must paint fire with the shipped profile.

Compiz 0.8 never grabs buttons for a configured shortcut, so a shortcut only
works when its plug-in is allowed to start. The ezoom smooth-scroll fix takes a
screen-wide pointer grab for the Shift+Super chord alone, and firepaint refuses
to initiate while any other screen grab exists. The shipped patch queue must
keep that grab from covering a press on a button that is not a wheel button.
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
QUEUE = ROOT / "patches/compiz-plugins-main"
YIELD_PATCH = QUEUE / "0002-ezoom-wheel-grab-yields-to-other-buttons.patch"
WHEEL_GRAB = "ezoom-wheel"

spec = importlib.util.spec_from_file_location(
    "migration", ROOT / "overlays/usr/lib/spaced-linux/migrate-desktop.py")
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


def ini_values(text):
    """Every 'key = value' assignment in the Compiz profile."""
    return re.findall(r"(?m)^([a-z0-9_]+)\s*=\s*(.+?)\s*$", text)


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.text = PROFILE.read_text(encoding="utf-8")

    def test_fire_writing_uses_the_documented_shortcut(self):
        self.assertIn("as_initiate_button = <Shift><Super>Button1", self.text)
        self.assertIn("as_clear_button = <Shift><Super>Button3", self.text)
        self.assertIn("firepaint", self.text)

    def test_the_zoom_chord_that_takes_the_grab_is_unchanged(self):
        # The grab is taken for this chord, so the fix may not move it.
        self.assertIn("as_zoom_in_button = <Shift><Super>Button4", self.text)
        self.assertIn("as_zoom_out_button = <Shift><Super>Button5", self.text)
        self.assertIn("as_zoom_in_key = <Shift><Super>Up", self.text)

    def test_no_other_action_claims_shift_super_left_drag(self):
        claimants = [key for key, value in ini_values(self.text)
                     if value == "<Shift><Super>Button1"]
        self.assertEqual(claimants, ["as_initiate_button"],
                         "another Compiz action shares the fire shortcut")

    def test_move_resize_and_screenshot_shortcuts_are_untouched(self):
        self.assertIn("as_initiate_button = <Alt>Button1", self.text)
        self.assertIn("as_initiate_button = <Super>Button3", self.text)
        self.assertIn("as_initiate_button = <Control><Shift>Button1", self.text)


class PatchQueueTests(unittest.TestCase):
    def setUp(self):
        self.queue = sorted(QUEUE.glob("*.patch"))
        self.yield_patch = YIELD_PATCH.read_text(encoding="utf-8")

    def test_the_wheel_grab_patch_is_in_the_shipped_queue(self):
        self.assertIn(YIELD_PATCH.name, [path.name for path in self.queue])
        self.assertIn("--- a/src/ezoom/ezoom.c", self.yield_patch)
        self.assertIn("+++ b/src/ezoom/ezoom.c", self.yield_patch)

    def test_the_grab_yields_while_a_non_wheel_button_is_pressed(self):
        for needle in ("zoomWheelButton",
                       "if (event->type == ButtonPress)",
                       "removeScreenGrab (s, zs->wheelGrabIndex, NULL);",
                       "zs->wheelGrabIndex = 0;"):
            self.assertIn(needle, self.yield_patch)

    def test_the_grab_is_taken_again_when_the_button_comes_back_up(self):
        self.assertIn("if (event->type == ButtonRelease)", self.yield_patch)
        self.assertIn("zoomUpdateWheelGrab (d, ((XButtonEvent *) event)->state);",
                      self.yield_patch)

    def test_smooth_scroll_suppression_is_not_reverted(self):
        # Removing the chord grab would fix fire and re-break issue #371.
        smooth = (QUEUE / "0001-ezoom-consume-smooth-scroll.patch"
                  ).read_text(encoding="utf-8")
        self.assertIn(f'pushScreenGrab (s, None, "{WHEEL_GRAB}")', smooth)
        self.assertIn(f'otherScreenGrabExist (s, "{WHEEL_GRAB}", NULL)', smooth)

    def test_the_rebuilt_package_version_agrees_across_the_pipeline(self):
        versions = set()
        for script in ("scripts/iso/build-compiz-plugins-main.sh",
                       "scripts/iso/stage-compiz-plugins-main.sh"):
            match = re.search(r"(?m)^VERSION=(.+)$",
                              Path(ROOT / script).read_text(encoding="utf-8"))
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

    def test_the_recorded_workaround_is_restored(self):
        self.write("[core]\nas_active_plugins=core;ccp;firepaint;\n"
                   "[firepaint]\nas_initiate_button=<Control><Alt><Shift>Button1\n")
        migration.migrate_firepaint(self.profile)
        self.assertIn("as_initiate_button=<Shift><Super>Button1",
                      self.profile.read_text(encoding="utf-8"))

    def test_a_personal_binding_is_never_overwritten(self):
        self.write("[firepaint]\nas_initiate_button=<Alt><Shift>Button1\n")
        migration.migrate_firepaint(self.profile)
        text = self.profile.read_text(encoding="utf-8")
        self.assertIn("as_initiate_button=<Alt><Shift>Button1", text)
        self.assertNotIn("as_initiate_button=<Shift><Super>Button1", text)

    def test_an_upgraded_account_gets_the_default_without_losing_other_keys(self):
        self.write("[firepaint]\nas_clear_button=<Shift><Super>Button3\n"
                   "s0_num_particles=1000\n")
        migration.migrate_firepaint(self.profile)
        text = self.profile.read_text(encoding="utf-8")
        self.assertIn("as_initiate_button=<Shift><Super>Button1", text)
        self.assertIn("s0_num_particles=1000", text)

    def test_the_migration_default_matches_the_shipped_profile(self):
        self.assertEqual(migration.FIREPAINT_INITIATE, "<Shift><Super>Button1")
        self.assertIn(f"as_initiate_button = {migration.FIREPAINT_INITIATE}",
                      PROFILE.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
