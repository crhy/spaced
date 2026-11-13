import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ElogindBackportTests(unittest.TestCase):
    def test_patch_hunk_line_counts_are_valid(self):
        """Catch malformed patches before the privileged package build does."""
        hunk_header = re.compile(r"^@@ -(?:\d+)(?:,(\d+))? \+(?:\d+)(?:,(\d+))? @@")

        for patch_path in sorted((ROOT / "patches/elogind").glob("*.patch")):
            lines = patch_path.read_text().splitlines()
            hunks = 0
            index = 0
            while index < len(lines):
                match = hunk_header.match(lines[index])
                if not match:
                    index += 1
                    continue

                hunks += 1
                expected_old = int(match.group(1) or 1)
                expected_new = int(match.group(2) or 1)
                actual_old = actual_new = 0
                index += 1
                while index < len(lines):
                    line = lines[index]
                    if line.startswith("@@ ") or line.startswith("diff --git "):
                        break
                    if (actual_old, actual_new) == (expected_old, expected_new):
                        break
                    self.assertTrue(
                        line.startswith((" ", "+", "-", "\\")),
                        f"{patch_path.name}: malformed hunk line {index + 1}: {line!r}",
                    )
                    if line.startswith((" ", "-")):
                        actual_old += 1
                    if line.startswith((" ", "+")):
                        actual_new += 1
                    index += 1

                self.assertEqual(
                    (actual_old, actual_new),
                    (expected_old, expected_new),
                    f"{patch_path.name}: incorrect line counts in hunk ending near line {index + 1}",
                )
            self.assertGreater(hunks, 0, f"{patch_path.name}: patch contains no hunks")

    def test_sources_have_pinned_sha256_hashes(self):
        entries = (ROOT / "patches/elogind/sources.sha256").read_text().splitlines()
        self.assertEqual(len(entries), 3)
        for entry in entries:
            digest, filename = entry.split(maxsplit=1)
            self.assertRegex(digest, r"^[0-9a-f]{64}$")
            self.assertRegex(filename, r"^elogind_257\.13(?:-1)?\.(?:dsc|orig\.tar\.gz|debian\.tar\.xz)$")

    def test_patch_is_the_upstream_null_dereference_fix(self):
        patch = (ROOT / "patches/elogind/0001-fix-poweroff-reboot-segfault.patch").read_text()
        self.assertIn("f5d1d8413df17a9548b205a80f715174ded00762", patch)
        self.assertIn("+        log_info(\"Operation '%s' finished.\", handle_action_to_string(a->handle));", patch)
        self.assertNotIn("+        log_info(\"Operation '%s' finished.\", handle_action_to_string(m->delayed_action->handle));", patch)
        self.assertIn("+                        m->sleep_fork_action = NULL;", patch)
        self.assertIn("+                        m->action_job = mfree(m->action_job);", patch)

    def test_xml_build_fix_is_pinned(self):
        patch = (ROOT / "patches/elogind/0002-enable-xml-entity-resolution.patch").read_text()
        self.assertIn("5b6579284f92770af5999bbcbb9169ca96f78643", patch)
        self.assertIn("XMLParser(resolve_entities=True)", patch)

    def test_build_and_stage_versions_match_and_future_release_supersedes(self):
        build = (ROOT / "scripts/iso/build-elogind.sh").read_text()
        stage = (ROOT / "scripts/iso/stage-elogind.sh").read_text()
        versions = [re.search(r"^VERSION=(\S+)$", text, re.M).group(1) for text in (build, stage)]
        self.assertEqual(versions, ["257.13-1+spaced11.26.1"] * 2)
        # Debian compares the upstream 257.14 component before the local suffix.
        self.assertLess(tuple(map(int, versions[0].split("-", 1)[0].split("."))), (257, 14))
        for package in ("elogind", "libelogind0", "libelogind-compat", "libpam-elogind"):
            self.assertIn(package, stage)

    def test_source_and_binary_publication_are_mandatory(self):
        local = (ROOT / "scripts/iso/build-local-packages.sh").read_text()
        repo = (ROOT / "scripts/build-apt-repo.sh").read_text()
        self.assertIn('stage-elogind.sh', local)
        self.assertIn('elogind_artifacts', repo)
        self.assertIn('elogind_*.dsc', repo)

    def test_chroot_supports_mount_namespace_tests(self):
        chroot = (ROOT / "scripts/iso/build-marco-chroot.sh").read_text()
        self.assertIn('mount --bind "$CHROOT" "$CHROOT"', chroot)
        self.assertIn('mount --make-rslave "$CHROOT"', chroot)

    def test_service_free_build_runs_all_non_live_elogind_tests(self):
        build = (ROOT / "scripts/iso/build-elogind.sh").read_text()
        self.assertIn('DEB_BUILD_OPTIONS="${DEB_BUILD_OPTIONS:+$DEB_BUILD_OPTIONS }nocheck"', build)
        self.assertIn('test["name"] != "test-login"', build)
        self.assertIn('len(tests) != 272 or len(names) != 271', build)
        self.assertIn('"--no-rebuild", "--print-errorlogs"', build)


if __name__ == "__main__":
    unittest.main()
