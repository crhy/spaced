"""Issue #158: the Compiz tutorial video is linked from the help surfaces.

The link must stay a plain https URL: an embedded YouTube player would add a
third-party script and make the shipped help depend on YouTube being reachable.
"""
from pathlib import Path
import re
import unittest

REPO = Path(__file__).resolve().parents[1]
VIDEO_URL = "https://youtu.be/csKKNzKwrMg"
VIDEO_TITLE = "Compiz on Spaced Linux: a 5-minute tour"

# Where a user goes looking for help with the Compiz desktop.
HTML_SURFACES = ("website/help.html", "website/index.html")
MARKDOWN_SURFACES = ("docs/COMPIZ.md", "docs/HELP.md", "README.md")

# Embedded-player forms that must never replace the plain link.
EMBEDDING = ("<iframe", "youtube.com/embed", "player.youtube.com", "youtube-nocookie.com")


class CompizTutorialLinkTests(unittest.TestCase):
    def text(self, relative):
        return (REPO / relative).read_text(encoding="utf-8")

    def test_video_is_linked_from_every_help_surface(self):
        missing = [
            path
            for path in HTML_SURFACES + MARKDOWN_SURFACES
            if VIDEO_URL not in self.text(path)
        ]
        self.assertEqual(missing, [], "help surfaces missing the Compiz tutorial link")

    def test_help_page_and_compiz_guide_name_the_video(self):
        for relative in ("website/help.html", "docs/COMPIZ.md"):
            self.assertIn(
                VIDEO_TITLE,
                self.text(relative),
                f"{relative} does not title the video it links",
            )

    def test_link_is_a_plain_https_link(self):
        for relative in HTML_SURFACES:
            self.assertIn(
                f'<a href="{VIDEO_URL}">',
                self.text(relative),
                f"{relative} does not carry the video as a plain href",
            )
        for relative in MARKDOWN_SURFACES:
            self.assertIn(
                f"]({VIDEO_URL})",
                self.text(relative),
                f"{relative} does not carry the video as a plain Markdown link",
            )

    def test_no_help_surface_embeds_the_player(self):
        for relative in HTML_SURFACES + MARKDOWN_SURFACES:
            text = self.text(relative)
            for form in EMBEDDING:
                self.assertNotIn(form, text, f"{relative} embeds a YouTube player ({form})")

    def test_the_only_youtu_be_link_is_the_tutorial(self):
        for relative in ("website/help.html", "docs/COMPIZ.md"):
            self.assertEqual(
                re.findall(r"https://youtu\.be/([A-Za-z0-9_-]+)", self.text(relative)),
                ["csKKNzKwrMg"],
                f"{relative} does not link exactly the tutorial video",
            )


if __name__ == "__main__":
    unittest.main()
