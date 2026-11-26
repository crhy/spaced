"""Structural tests for the ordered live-image configuration phases."""
from pathlib import Path
import re
import stat
import unittest


ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATOR = ROOT / "scripts/iso/01-configure.chroot"
HELPER_DIR = ROOT / "scripts/iso/configure.d"
EXPECTED_HELPERS = [
    "10-identity-desktop.sh",
    "20-flatpak.sh",
    "30-live-user.sh",
    "40-desktop-cleanup.sh",
    "50-services-boot.sh",
    "90-clean.sh",
]


class IsoConfigurePhaseTests(unittest.TestCase):
    def helper_paths(self):
        return sorted(HELPER_DIR.glob("*.sh"))

    def test_phase_names_make_order_explicit(self):
        self.assertEqual([path.name for path in self.helper_paths()],
                         EXPECTED_HELPERS)

    def test_orchestrator_is_strict_and_removes_build_only_helpers(self):
        text = ORCHESTRATOR.read_text(encoding="utf-8")
        self.assertIn("set -euo pipefail", text)
        self.assertIn('helpers=("$helper_dir"/*.sh)', text)
        self.assertIn('for helper in "${helpers[@]}"', text)
        self.assertIn('rm -rf "$helper_dir"', text)

    def test_every_phase_is_strict_and_executable(self):
        for path in self.helper_paths():
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertIn("set -euo pipefail", text)
                self.assertTrue(path.stat().st_mode & stat.S_IXUSR)

    def test_hook_never_downloads_rolling_packages(self):
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in [ORCHESTRATOR, *self.helper_paths()]
        )
        self.assertIsNone(re.search(r"\bapt(?:-get)?\s+install\b", combined))
        self.assertIn('dpkg -s "$package"', combined)
        self.assertIn("mate-session-manager", combined)

    def test_makefile_stages_orchestrator_and_helpers(self):
        text = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn("scripts/iso/01-configure.chroot", text)
        self.assertIn("scripts/iso/configure.d/*.sh", text)
        self.assertIn("live-build-configure.d/", text)

    def test_home_traversal_policy_is_unchanged(self):
        # The 11.26.3-2 scope explicitly retains the existing issue #297
        # policy. A later ACL migration must be an intentional, tested change.
        text = (HELPER_DIR / "30-live-user.sh").read_text(encoding="utf-8")
        self.assertIn("chmod 0711 /home/user", text)


if __name__ == "__main__":
    unittest.main()
