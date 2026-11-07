import json
import re
import runpy
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / "overlays"
HELPER = OVERLAY / "usr/local/bin/spaced-theme-palette"
THEME_ROOT = OVERLAY / "usr/share/themes"
REGISTRY = OVERLAY / "usr/share/spaced-themes/themes.json"
SWITCHER = OVERLAY / "usr/local/bin/spaced-switch-theme"
MONITOR = OVERLAY / "usr/local/bin/spaced-theme-monitor"

LIBADWAITA_NAMES = (
    "window_bg_color",
    "window_fg_color",
    "view_bg_color",
    "view_fg_color",
    "headerbar_bg_color",
    "headerbar_fg_color",
    "sidebar_bg_color",
    "card_bg_color",
    "popover_bg_color",
    "dialog_bg_color",
    "accent_bg_color",
    "accent_fg_color",
    "accent_color",
)
GTK_NAMES = (
    "theme_bg_color",
    "theme_base_color",
    "theme_fg_color",
    "theme_selected_bg_color",
    "theme_selected_fg_color",
)
DEFINE_RE = re.compile(r"^@define-color ([a-z_]+) (#[0-9a-f]{6});$", re.M)
HEADER_RE = re.compile(r"\A/\* spaced-theme: (\S+) dark=([01]) \*/")


def gtk_colors(theme_name):
    """Resolve the five named colours straight out of the theme stylesheet."""
    text = (THEME_ROOT / theme_name / "gtk-3.0/gtk.css").read_text(encoding="utf-8")
    definitions = dict(re.findall(r"@define-color\s+([A-Za-z_][\w-]*)\s+([^;]+);", text))
    colors = {}
    for name in GTK_NAMES:
        raw = definitions[name].strip()
        if raw.startswith("@"):
            raw = definitions[raw[1:].strip()].strip()
        colors[name] = raw.lower()
    return colors


class RustDeskTomlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.update = staticmethod(runpy.run_path(str(HELPER))["rustdesk_toml_with_theme"])

    def assert_only_theme_changed(self, source):
        original = tomllib.loads(source)
        expected = {**original, "options": {**original.get("options", {}), "theme": "dark"}}
        updated = self.update(source, "dark")
        self.assertEqual(expected, tomllib.loads(updated))
        self.assertEqual(updated, self.update(updated, "dark"))
        return updated

    def test_missing_final_newline_is_added_before_the_new_key(self):
        for source in ('[options]', '[options]\nfoo = "bar"', '[options]\n# keep this comment'):
            with self.subTest(source=source):
                self.assertEqual(source + '\ntheme = "dark"\n',
                                 self.assert_only_theme_changed(source))

    def test_commented_and_quoted_headers_are_preserved(self):
        for header in ('[options] # settings', '[ options ] # settings',
                       '["options"] # settings', "['options'] # settings"):
            with self.subTest(header=header):
                source = header + '\nfoo = "bar"\n'
                self.assertEqual(source + 'theme = "dark"\n',
                                 self.assert_only_theme_changed(source))

    def test_comment_on_next_table_does_not_change_its_theme(self):
        source = '[options]\nfoo = "bar"\n[ui_flutter] # keep this table\ntheme = "other"\n'
        self.assertEqual(
            '[options]\nfoo = "bar"\ntheme = "dark"\n'
            '[ui_flutter] # keep this table\ntheme = "other"\n',
            self.assert_only_theme_changed(source))

    def test_quoted_theme_key_is_updated_without_a_duplicate(self):
        for key in ('theme', '"theme"', "'theme'"):
            with self.subTest(key=key):
                self.assert_only_theme_changed('[options]\n' + key + ' = "light"\n')

    def test_no_options_table_is_added_without_changing_other_values(self):
        for source in ('', 'remote_id = "123"', '[ui_flutter]\ntheme = "other"'):
            with self.subTest(source=source):
                self.assert_only_theme_changed(source)

    def test_unrecognized_layouts_and_invalid_input_are_left_untouched(self):
        for source in (
            'options = {theme = "light", foo = "bar"}\n',
            'options = "unexpected"\n',
            '[options]\ninvalid toml',
            # A header-looking line inside a multiline value must not be edited.
            'note = """\n[options]\ntheme = "light"\n"""\n',
            '[options]\nnotes = """\ntheme = "light"\n"""\n',
        ):
            with self.subTest(source=source):
                self.assertEqual(source, self.update(source, "dark"))


class PaletteGeneratorTests(unittest.TestCase):
    """Run the generator for every catalogue theme, headless, under build/."""

    @classmethod
    def setUpClass(cls):
        cls.themes = json.loads(REGISTRY.read_text(encoding="utf-8"))["themes"]
        build_root = ROOT / "build"
        build_root.mkdir(exist_ok=True)
        cls._workspace = tempfile.TemporaryDirectory(
            prefix="libadwaita-palette-", dir=str(build_root))
        cls.workspace = Path(cls._workspace.name)

    @classmethod
    def tearDownClass(cls):
        cls._workspace.cleanup()

    def run_helper(self, gtk_theme, config_home, themes_root=THEME_ROOT, themes_json=REGISTRY):
        env = {
            # Keep Path.home() and Flatpak state inside the disposable fixture.
            "HOME": str(config_home.parent),
            "XDG_CONFIG_HOME": str(config_home),
            "SPACED_THEMES_ROOT": str(themes_root),
            "SPACED_THEMES_JSON": str(themes_json),
            # The image must not pick up bytecode compiled during a test run.
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        return subprocess.run(
            [sys.executable, str(HELPER), gtk_theme],
            env=env, capture_output=True, text=True, timeout=60)

    def generate(self, gtk_theme):
        config_home = self.workspace / f"config-{gtk_theme}"
        result = self.run_helper(gtk_theme, config_home)
        self.assertEqual(0, result.returncode,
                        f"{gtk_theme}: {result.stdout}{result.stderr}")
        state_dir = config_home / "spaced"
        css_path = state_dir / "libadwaita.css"
        json_path = state_dir / "theme.json"
        self.assertTrue(css_path.is_file(), css_path)
        self.assertTrue(json_path.is_file(), json_path)
        return css_path, json_path

    def test_css_is_complete_for_every_catalogue_theme(self):
        for theme in self.themes:
            with self.subTest(theme=theme["id"]):
                css_path, json_path = self.generate(theme["gtk_theme"])
                css_text = css_path.read_text(encoding="utf-8")
                header = HEADER_RE.match(css_text)
                self.assertIsNotNone(header, f"{theme['gtk_theme']}: bad header line")
                self.assertEqual(theme["gtk_theme"], header.group(1))
                self.assertEqual(str(int(bool(theme["dark"]))), header.group(2))

                colors = dict(DEFINE_RE.findall(css_text))
                for name in LIBADWAITA_NAMES:
                    self.assertIn(name, colors, f"{theme['gtk_theme']}: missing {name}")
                self.assertEqual(len(LIBADWAITA_NAMES), len(colors),
                                f"{theme['gtk_theme']}: unexpected @define-color entries")

                source = gtk_colors(theme["gtk_theme"])
                self.assertEqual(source["theme_bg_color"], colors["window_bg_color"])
                self.assertEqual(source["theme_fg_color"], colors["window_fg_color"])
                self.assertEqual(source["theme_base_color"], colors["view_bg_color"])
                self.assertEqual(source["theme_selected_bg_color"], colors["accent_bg_color"])
                self.assertEqual(source["theme_selected_fg_color"], colors["accent_fg_color"])
                # Raised surfaces must differ from the view background but stay
                # between it and the foreground, otherwise cards are invisible.
                self.assertNotEqual(colors["view_bg_color"], colors["card_bg_color"])
                self.assertNotEqual(colors["view_bg_color"], colors["sidebar_bg_color"])

    def test_json_sidecar_matches_the_css(self):
        for theme in self.themes:
            with self.subTest(theme=theme["id"]):
                _, json_path = self.generate(theme["gtk_theme"])
                payload = json.loads(json_path.read_text(encoding="utf-8"))
                self.assertEqual({"gtk_theme", "dark", "colors"}, set(payload))
                self.assertEqual(theme["gtk_theme"], payload["gtk_theme"])
                self.assertIs(theme["dark"], payload["dark"])
                self.assertEqual(len(LIBADWAITA_NAMES), len(payload["colors"]))
                for value in payload["colors"].values():
                    self.assertRegex(value, r"\A#[0-9a-f]{6}\Z")

    def test_win11_presets_keep_their_catalogue_dark_flag(self):
        for theme_id, expected in (("win11-light", "0"), ("win11-dark", "1")):
            theme = next(item for item in self.themes if item["id"] == theme_id)
            css_path, _ = self.generate(theme["gtk_theme"])
            self.assertIn(f"dark={expected}", css_path.read_text(encoding="utf-8").splitlines()[0])

    def test_rustdesk_native_and_flatpak_profiles_follow_the_theme(self):
        dark_theme = next(item for item in self.themes if item["dark"])
        light_theme = next(item for item in self.themes if not item["dark"])
        config_home = self.workspace / "config-rustdesk"
        native = config_home / "RustDesk/RustDesk_local.toml"
        flatpak = (config_home / "../.var/app/com.rustdesk.RustDesk/config/RustDesk/"
                   "RustDesk_local.toml").resolve()

        native.parent.mkdir(parents=True, exist_ok=True)
        native.write_text(
            'remote_id = "123"\n\n[options]\nfoo = "bar"\ntheme = "light"\n\n[ui_flutter]\n',
            encoding="utf-8")
        result = self.run_helper(dark_theme["gtk_theme"], config_home)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn('remote_id = "123"', native.read_text(encoding="utf-8"))
        self.assertIn('foo = "bar"', native.read_text(encoding="utf-8"))
        self.assertEqual(1, native.read_text(encoding="utf-8").count('theme = "dark"'))
        self.assertEqual('[options]\ntheme = "dark"\n', flatpak.read_text(encoding="utf-8"))

        result = self.run_helper(light_theme["gtk_theme"], config_home)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(1, native.read_text(encoding="utf-8").count('theme = "light"'))
        self.assertNotIn('theme = "dark"', native.read_text(encoding="utf-8"))
        self.assertEqual('[options]\ntheme = "light"\n', flatpak.read_text(encoding="utf-8"))

    def test_rustdesk_theme_is_added_to_an_existing_options_section(self):
        theme = next(item for item in self.themes if item["dark"])
        config_home = self.workspace / "config-rustdesk-options"
        profile = config_home / "RustDesk/RustDesk_local.toml"
        profile.parent.mkdir(parents=True, exist_ok=True)
        profile.write_text('[options]\nfoo = "bar"\n[ui_flutter]\nscale = "1"\n',
                           encoding="utf-8")
        result = self.run_helper(theme["gtk_theme"], config_home)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(
            '[options]\nfoo = "bar"\ntheme = "dark"\n[ui_flutter]\nscale = "1"\n',
            profile.read_text(encoding="utf-8"))

    def test_invalid_rustdesk_profile_is_preserved_and_does_not_block_the_palette(self):
        theme = next(item for item in self.themes if item["dark"])
        for number, original in enumerate((b'[options]\ninvalid toml', b'\xff\xfe')):
            with self.subTest(original=original):
                config_home = self.workspace / f"config-rustdesk-invalid-{number}"
                profile = config_home / "RustDesk/RustDesk_local.toml"
                profile.parent.mkdir(parents=True, exist_ok=True)
                profile.write_bytes(original)
                result = self.run_helper(theme["gtk_theme"], config_home)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual(original, profile.read_bytes())
                self.assertTrue((config_home / "spaced/theme.json").is_file())

    def test_one_level_of_at_name_indirection_is_followed(self):
        themes_root = self.workspace / "themes-ref"
        css = themes_root / "Probe-Ref" / "gtk-3.0" / "gtk.css"
        css.parent.mkdir(parents=True, exist_ok=True)
        css.write_text(
            "@define-color base_ref #111827;\n"
            "@define-color theme_bg_color @base_ref;\n"
            "@define-color theme_base_color @base_ref;\n"
            "@define-color theme_fg_color #f3f3f3;\n"
            "@define-color theme_selected_bg_color #005fb8;\n"
            "@define-color theme_selected_fg_color @theme_fg_color;\n",
            encoding="utf-8")
        config_home = self.workspace / "config-ref"
        css_path, json_path = (config_home / "spaced" / name for name in
                               ("libadwaita.css", "theme.json"))
        result = self.run_helper("Probe-Ref", config_home, themes_root=themes_root)
        self.assertEqual(0, result.returncode, result.stderr)
        colors = dict(DEFINE_RE.findall(css_path.read_text(encoding="utf-8")))
        self.assertEqual("#111827", colors["window_bg_color"])
        self.assertEqual("#f3f3f3", colors["accent_fg_color"])
        # No catalogue entry: the dark flag falls back to the stylesheet itself.
        self.assertIn("dark=1", css_path.read_text(encoding="utf-8").splitlines()[0])
        self.assertIs(True, json.loads(json_path.read_text(encoding="utf-8"))["dark"])

    def test_incomplete_stylesheet_fails_without_touching_the_old_palette(self):
        themes_root = self.workspace / "themes-bad"
        css = themes_root / "Probe-Bad" / "gtk-3.0" / "gtk.css"
        css.parent.mkdir(parents=True, exist_ok=True)
        css.write_text("@define-color theme_bg_color #101010;\n", encoding="utf-8")

        config_home = self.workspace / "config-bad"
        # Seed the state directory with sentinel content first.
        state_dir = config_home / "spaced"
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "libadwaita.css").write_text("SENTINEL\n", encoding="utf-8")
        (state_dir / "theme.json").write_text("SENTINEL\n", encoding="utf-8")

        result = self.run_helper("Probe-Bad", config_home, themes_root=themes_root)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("theme_base_color", result.stderr)
        self.assertEqual("SENTINEL\n", (state_dir / "libadwaita.css").read_text(encoding="utf-8"))
        self.assertEqual("SENTINEL\n", (state_dir / "theme.json").read_text(encoding="utf-8"))
        self.assertEqual([], [entry for entry in state_dir.iterdir() if entry.name.startswith(".")])

    def test_missing_argument_is_a_clean_usage_error(self):
        result = subprocess.run([sys.executable, str(HELPER)],
                                env={"XDG_CONFIG_HOME": str(self.workspace / "config-usage")},
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(2, result.returncode)
        self.assertIn("Usage:", result.stderr)
        self.assertFalse((self.workspace / "config-usage").exists())

    def test_switcher_and_monitor_publish_the_palette(self):
        switcher = SWITCHER.read_text(encoding="utf-8")
        monitor = MONITOR.read_text(encoding="utf-8")
        self.assertIn('/usr/local/bin/spaced-theme-palette "$gtk_theme" 2>/dev/null || true', switcher)
        self.assertIn('/usr/local/bin/spaced-theme-palette "$LAST" 2>/dev/null || true', monitor)
        # The switcher must publish after the gsettings changes, not before them.
        self.assertLess(switcher.index('gsettings set org.mate.panel default-layout'),
                        switcher.index("spaced-theme-palette"))
        self.assertLess(monitor.index('apply_for_gtk "$LAST"'), monitor.index("spaced-theme-palette"))


if __name__ == "__main__":
    unittest.main()
