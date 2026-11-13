"""The published site must not ship megabytes for small pictures (audit a12 W02-W19).

`scripts/build-site.sh` assembles `dist/` (git-ignored); this test builds it, walks
every local reference in the three pages and `styles.css`, and keeps the image and
total budgets in check.  `dist/` is removed again afterwards.
"""
from pathlib import Path
import re
import shutil
import subprocess
import unittest

REPO = Path(__file__).resolve().parents[1]
DIST = REPO / "dist"
PAGES = ("index.html", "themes.html", "help.html")
IMAGE_SUFFIXES = {".avif", ".gif", ".ico", ".jpeg", ".jpg", ".png", ".svg", ".webp"}
MAX_IMAGE_BYTES = 400 * 1024
MAX_DIST_BYTES = 5 * 1024 * 1024

# Values starting like this are not files inside dist/.
EXTERNAL = ("http://", "https://", "//", "#", "data:", "mailto:", "bitcoin:", "tel:", "javascript:")


def local_path(value):
    """The local file a single URL asks the server for, or None (external, #, bare /).

    `?v=...` cache-busting suffixes and #fragments are ignored.
    """
    part = value.strip()
    if not part or part.lower().startswith(EXTERNAL):
        return None
    path = part.split("?")[0].split("#")[0].strip()
    return path if path and path != "/" else None


def referenced_paths(html, css):
    """Every local path the pages and the stylesheet ask the server for."""
    found = set()
    for attr in ("src", "href", "data-image"):
        for match in re.finditer(rf'\b{attr}="([^"]*)"', html):
            path = local_path(match.group(1))
            if path:
                found.add(path)
    for match in re.finditer(r'\bsrcset="([^"]*)"', html):
        for candidate in match.group(1).split(","):
            tokens = candidate.split()
            if not tokens:
                continue
            path = local_path(tokens[0])
            if path:
                found.add(path)
    for match in re.finditer(r"""url\(\s*['"]?([^'")]+)""", css):
        path = local_path(match.group(1))
        if path:
            found.add(path)
    return found


class WebsiteAssetBudgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = subprocess.run(
            ["bash", str(REPO / "scripts" / "build-site.sh")],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if result.returncode != 0:
            raise AssertionError(f"scripts/build-site.sh failed: {result.stderr}")
        if not DIST.is_dir():
            raise AssertionError("scripts/build-site.sh did not create dist/")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(DIST, ignore_errors=True)

    def pages(self):
        for page in PAGES:
            yield page, (DIST / page).read_text(encoding="utf-8")

    def css(self):
        return (DIST / "styles.css").read_text(encoding="utf-8")

    def test_every_local_reference_resolves_in_dist(self):
        html = "\n".join(text for _, text in self.pages())
        missing = sorted(
            path
            for path in referenced_paths(html, self.css())
            if not (DIST / path.lstrip("/")).is_file()
        )
        self.assertEqual(missing, [], "pages reference files that dist/ does not contain")

    def test_no_referenced_image_is_larger_than_400_kb(self):
        html = "\n".join(text for _, text in self.pages())
        oversized = []
        for path in sorted(referenced_paths(html, self.css())):
            target = DIST / path.lstrip("/")
            if target.suffix.lower() not in IMAGE_SUFFIXES or not target.is_file():
                continue
            size = target.stat().st_size
            if size > MAX_IMAGE_BYTES:
                oversized.append(f"{path} is {size} bytes")
        self.assertEqual(oversized, [], "referenced images must stay under 400 KB")

    def test_every_img_with_a_src_carries_width_and_height(self):
        unsized = []
        for page, text in self.pages():
            for match in re.finditer(r"<img\b[^>]*>", text, re.I):
                tag = match.group(0)
                src = re.search(r'\bsrc="([^"]*)"', tag, re.I)
                if not src or not src.group(1).strip():
                    continue
                for attribute in ("width", "height"):
                    if not re.search(rf'\b{attribute}="\d+"', tag, re.I):
                        unsized.append(f"{page}: {src.group(1)} has no {attribute}")
        self.assertEqual(unsized, [], "<img> elements need intrinsic width and height")

    def test_lightbox_images_have_no_empty_src(self):
        for page, text in self.pages():
            self.assertNotIn('src=""', text, f"{page} ships an empty src attribute")

    def test_total_dist_size_stays_under_5_mb(self):
        total = sum(p.stat().st_size for p in DIST.rglob("*") if p.is_file())
        self.assertLess(total, MAX_DIST_BYTES, f"dist/ is {total} bytes")


if __name__ == "__main__":
    unittest.main()
