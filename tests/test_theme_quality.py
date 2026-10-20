import json
import hashlib
import math
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / "overlays"
THEME_ROOT = OVERLAY / "usr/share/themes"
WALLPAPER_ROOT = OVERLAY / "usr/share/backgrounds/spaced"
REGISTRY = OVERLAY / "usr/share/spaced-themes/themes.json"


def relative_luminance(color):
    channels = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    channels = [value / 12.92 if value <= 0.04045
                else math.pow((value + 0.055) / 1.055, 2.4)
                for value in channels]
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast(first, second):
    light, dark = sorted((relative_luminance(first), relative_luminance(second)),
                         reverse=True)
    return (light + 0.05) / (dark + 0.05)


class ThemeQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.themes = json.loads(REGISTRY.read_text(encoding="utf-8"))["themes"]

    def test_registry_is_unique_and_complete(self):
        self.assertEqual(13, len(self.themes))
        for key in ("id", "name", "gtk_theme"):
            values = [theme[key] for theme in self.themes]
            self.assertEqual(len(values), len(set(values)), f"duplicate {key}")
        self.assertIn("win7-aero-dark", {theme["id"] for theme in self.themes})

    def test_registered_assets_exist_and_use_canonical_wallpaper_directory(self):
        for theme in self.themes:
            with self.subTest(theme=theme["id"]):
                theme_root = THEME_ROOT / theme["gtk_theme"]
                for relative in ("index.theme", "gtk-2.0/gtkrc", "gtk-3.0/gtk.css",
                                 "gtk-3.0/index.theme", "metacity-1/metacity-theme-1.xml",
                                 "metacity-1/metacity-theme-3.xml", "preview.png"):
                    self.assertTrue((theme_root / relative).is_file(), relative)
                wallpaper = Path(theme["wallpaper"])
                self.assertEqual(Path("/usr/share/backgrounds/spaced"), wallpaper.parent)
                self.assertTrue((OVERLAY / wallpaper.relative_to("/")).is_file())
                layout = OVERLAY / "usr/share/mate-panel/layouts" / (
                    theme["panel_layout"] + ".layout")
                self.assertTrue(layout.is_file(), layout)

    def test_semantic_color_pairs_meet_normal_text_contrast(self):
        pairs = (("theme_bg_color", "theme_fg_color"),
                 ("theme_base_color", "theme_text_color"),
                 ("theme_selected_bg_color", "theme_selected_fg_color"),
                 ("theme_tooltip_bg_color", "theme_tooltip_fg_color"),
                 ("panel_bg_color", "panel_fg_color"))
        pattern = re.compile(r"@define-color\s+(\w+)\s+(#[0-9a-fA-F]{6})\s*;")
        for theme in self.themes:
            css = (THEME_ROOT / theme["gtk_theme"] / "gtk-3.0/gtk.css").read_text(
                encoding="utf-8")
            colors = dict(pattern.findall(css))
            for foreground, background in pairs:
                with self.subTest(theme=theme["id"], pair=(foreground, background)):
                    self.assertIn(foreground, colors)
                    self.assertIn(background, colors)
                    ratio = contrast(colors[foreground], colors[background])
                    self.assertGreaterEqual(ratio, 4.5, f"contrast is only {ratio:.2f}:1")

    def test_theme_identity_is_contiguous(self):
        for theme in self.themes:
            gtk_theme = theme["gtk_theme"]
            root = THEME_ROOT / gtk_theme
            metatheme = (root / "index.theme").read_text(encoding="utf-8")
            gtk_index = (root / "gtk-3.0/index.theme").read_text(encoding="utf-8")
            with self.subTest(theme=theme["id"]):
                self.assertIn(f"GtkTheme={gtk_theme}", metatheme)
                self.assertIn(f"MetacityTheme={gtk_theme}", metatheme)
                self.assertIn(f'gtk-theme-name = "{gtk_theme}"', gtk_index)
                icon_match = re.search(r"^IconTheme=(.+)$", metatheme, re.MULTILINE)
                self.assertIsNotNone(icon_match)
                icon_root = OVERLAY / "usr/share/icons" / icon_match.group(1)
                self.assertTrue(icon_root.is_dir(), f"missing icon theme: {icon_root}")

        # Older themes legitimately inherit an upstream Metacity engine name.
        # New themes must not accidentally retain the source theme's identity.
        aero_dark = (THEME_ROOT / "Spaced-Win7Aero-Dark" /
                     "metacity-1/metacity-theme-3.xml").read_text(encoding="utf-8")
        self.assertIn("<name>Spaced-Win7Aero-Dark</name>", aero_dark)

    def test_wallpapers_are_not_duplicated_in_legacy_source_tree(self):
        self.assertFalse((ROOT / "SpacedLinuxWallpapers").exists())
        aliases = ("SpacedBack.png", "SpacedBackLight.png",
                   "euclid-galaxy-garland.png", "spaced-orbit-4k.png")
        for name in aliases:
            with self.subTest(alias=name):
                self.assertTrue((WALLPAPER_ROOT / name).is_symlink())

        images = [path for path in WALLPAPER_ROOT.iterdir()
                  if path.is_file() and not path.is_symlink()]
        digests = {}
        for path in images:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertNotIn(digest, digests,
                             f"duplicate wallpaper bytes: {path.name} and {digests.get(digest)}")
            digests[digest] = path.name


if __name__ == "__main__":
    unittest.main()
