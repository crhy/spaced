"""The website may only show a checksum that was computed from the real ISO."""
from pathlib import Path
import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "website-release.sh"
START = "<!-- release-download:start -->"
END = "<!-- release-download:end -->"


class WebsiteReleaseStateTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.version = (REPO / "VERSION").read_text(encoding="utf-8").strip()
        self.iso = f"spaced-linux-{self.version}-amd64.iso"
        (self.root / "VERSION").write_text(
            (REPO / "VERSION").read_text(encoding="utf-8"), encoding="utf-8"
        )
        (self.root / "website").mkdir()
        self.index = self.root / "website" / "index.html"
        shutil.copyfile(REPO / "website" / "index.html", self.index)

    def run_script(self, *args):
        env = dict(os.environ, SPACED_WEBSITE_ROOT=str(self.root))
        return subprocess.run(
            ["bash", str(SCRIPT), *args],
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def text(self):
        return self.index.read_text(encoding="utf-8")

    def write_checksum_file(self, digest, name=None):
        directory = self.root / "build" / "iso"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (name or f"{self.iso}.sha256")
        path.write_text(f"{digest}  {self.iso}\n", encoding="utf-8")
        return path

    def assert_markers(self):
        for marker in (START, END):
            self.assertEqual(self.text().count(marker), 1, f"{marker} must appear once")

    def test_preview_hides_the_unvalidated_iso(self):
        result = self.run_script("preview")
        self.assertEqual(result.returncode, 0, result.stderr)
        page = self.text()
        self.assertIn(f"{self.version} PREVIEW", page.upper())
        self.assertNotIn("releases/download/", page)
        self.assertNotIn(self.iso, page)
        self.assertNotIn("SHA-256 <code>", page)
        self.assert_markers()
        # Re-running preview must not drift the file.
        before = self.index.read_bytes()
        self.assertEqual(self.run_script("preview").returncode, 0)
        self.assertEqual(self.index.read_bytes(), before)

    def test_publish_shows_the_checksum_from_the_sha256_file(self):
        self.assertEqual(self.run_script("preview").returncode, 0)
        digest = hashlib.sha256(b"the built iso").hexdigest()
        self.write_checksum_file(digest)
        result = self.run_script("publish")
        self.assertEqual(result.returncode, 0, result.stderr)
        page = self.text()
        self.assertIn(
            f"releases/download/v{self.version}/{self.iso}", page
        )
        self.assertIn(f"releases/tag/v{self.version}", page)
        self.assertIn(f"SHA-256 <code>{digest}</code>", page)
        self.assertIn(
            f"<p class=\"checksum\">Check your download: <code>sha256sum {self.iso}</code> "
            "must print this value.</p>",
            page,
        )
        self.assertNotIn(f"{self.version} PREVIEW", page.upper())
        self.assertIn(f"<p class=\"kicker\">SPACED LINUX \u00b7 {self.version}</p>", page)
        self.assert_markers()
        # Re-publishing the same checksum must not drift the file.
        before = self.index.read_bytes()
        self.assertEqual(self.run_script("publish").returncode, 0)
        self.assertEqual(self.index.read_bytes(), before)

    def test_publish_rejects_a_checksum_that_is_not_for_this_iso(self):
        self.assertEqual(self.run_script("preview").returncode, 0)
        before = self.index.read_bytes()
        good = hashlib.sha256(b"the built iso").hexdigest()
        for label, content in (
            ("63 hex digits", f"{good[:-1]}  {self.iso}\n"),
            ("another file name", f"{good}  spaced-linux-0.0-amd64.iso\n"),
            ("two lines", f"{good}  {self.iso}\n{good}  {self.iso}\n"),
        ):
            with self.subTest(label):
                broken = self.root / "broken.sha256"
                broken.write_text(content, encoding="utf-8")
                result = self.run_script("publish", str(broken))
                self.assertEqual(result.returncode, 1)
                self.assertEqual(self.index.read_bytes(), before)
        missing = self.root / "build" / "iso" / f"{self.iso}.sha256"
        result = self.run_script("publish", str(missing))
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.index.read_bytes(), before)

    @unittest.skipUnless(shutil.which("sha256sum"), "sha256sum is not installed")
    def test_publish_checks_the_iso_next_to_the_checksum_file(self):
        self.assertEqual(self.run_script("preview").returncode, 0)
        iso = self.root / "build" / "iso" / self.iso
        iso.parent.mkdir(parents=True)
        iso.write_bytes(b"the built iso")
        digest = hashlib.sha256(iso.read_bytes()).hexdigest()
        self.write_checksum_file(digest)
        self.assertEqual(self.run_script("publish").returncode, 0)
        self.assertIn(f"SHA-256 <code>{digest}</code>", self.text())
        # A checksum file that no longer matches the ISO must not be published.
        before = self.index.read_bytes()
        iso.write_bytes(b"a different iso")
        result = self.run_script("publish")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.index.read_bytes(), before)

    def test_preview_publish_preview_returns_the_first_preview(self):
        self.assertEqual(self.run_script("preview").returncode, 0)
        first = self.index.read_bytes()
        digest = hashlib.sha256(b"the built iso").hexdigest()
        self.write_checksum_file(digest)
        self.assertEqual(self.run_script("publish").returncode, 0)
        self.assertNotEqual(self.index.read_bytes(), first)
        self.assertEqual(self.run_script("preview").returncode, 0)
        self.assertEqual(self.index.read_bytes(), first)

    def test_unknown_command_prints_usage_and_changes_nothing(self):
        self.assertEqual(self.run_script("preview").returncode, 0)
        before = self.index.read_bytes()
        for argument in ("", "frobnicate", "publish --force extra"):
            with self.subTest(argument):
                result = self.run_script(*([argument] if argument else []))
                self.assertEqual(result.returncode, 2)
                self.assertIn("Usage:", result.stderr)
                self.assertEqual(self.index.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
