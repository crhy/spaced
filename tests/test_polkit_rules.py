"""GParted live-session polkit authorization regressions."""
import re
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
POLKIT_RULE = ROOT / "overlays/etc/polkit-1/rules.d/49-spaced-live-gparted.rules"


class GPartedPolkitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rule = POLKIT_RULE.read_text(encoding="utf-8")

    def test_file_exists(self):
        self.assertTrue(POLKIT_RULE.is_file(), "polkit rule file is missing")

    def test_allows_active_local_live_user(self):
        self.assertIn('subject.user == "user"', self.rule)
        self.assertIn("subject.local", self.rule)
        self.assertIn("subject.active", self.rule)

    def test_direct_gparted_action_is_allowed(self):
        self.assertIn('action.id == "org.gnome.gparted"', self.rule)

    def test_uses_action_lookup_not_details_dict(self):
        # The real polkit JavaScript API: action.lookup retrieves the
        # exec path annotation; details[...] is the deprecated form.
        self.assertIn('action.lookup("org.freedesktop.policykit.exec.path")', self.rule)
        self.assertNotIn('details["org.freedesktop.policykit.exec.path"]', self.rule)
        self.assertNotIn("details.get(", self.rule)

    def test_exec_path_targets_sbin_gparted(self):
        self.assertIn('"/usr/sbin/gparted"', self.rule)

    def test_policykit_exec_action_is_covered(self):
        self.assertIn('action.id == "org.freedesktop.policykit.exec"', self.rule)

    def test_returns_polkit_result_yes(self):
        self.assertIn("polkit.Result.YES", self.rule)

    def test_is_live_only_removed_by_calamares(self):
        cleanup = (ROOT / "overlays/etc/calamares/modules/shellprocess@spaced-cleanup.conf").read_text(
            encoding="utf-8")
        self.assertIn("49-spaced-live-gparted.rules", cleanup)

    def test_rule_structure_is_well_formed(self):
        # Must open and close the rule function, and return YES inside the guard
        self.assertIn("polkit.addRule(function(action, subject)", self.rule)
        self.assertIn("});", self.rule)
        # The subject guard must precede the action checks
        subject_pos = self.rule.index('subject.user == "user"')
        action_pos = self.rule.index('action.id == "org.gnome.gparted"')
        self.assertLess(subject_pos, action_pos)

    def test_no_broad_allow_any_user(self):
        # Must not allow GParted for arbitrary users
        self.assertNotIn("action.id == \"org.gnome.gparted\"",
                         self.rule.split("subject.user")[0],
                         "GParted allow must be guarded by subject.user")


if __name__ == "__main__":
    unittest.main()
