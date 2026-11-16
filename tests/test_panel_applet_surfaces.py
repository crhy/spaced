"""Issue #387: every shipped theme must let the panel's applets inherit the
panel's own background.

The Menu, clock/date, volume and show-desktop applets run out of process, so
each one arrives wrapped in its own host widget (`#PanelApplet`, `#PanelPlug`,
`NaTrayApplet` ...). If a theme paints those hosts, the user's panel fill or
panel picture stops at the applet edge and the sections read as grey slabs.
"""

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / "overlays"
THEME_ROOT = OVERLAY / "usr/share/themes"
REGISTRY = OVERLAY / "usr/share/spaced-themes/themes.json"

# The selector list proven in Spaced-Win7Aero-Dark/gtk-3.0/gtk.css.
HOST_SELECTORS = (
    ".mate-panel-menu-bar #PanelApplet",
    ".gnome-panel-menu-bar #PanelApplet",
    "#MatePanelWidget #PanelApplet",
    "PanelApplet",
    "MatePanelApplet",
    "NaTrayApplet",
    "#PanelPlug",
    "#PanelPlug > box",
    "#PanelPlug > widget",
    "#PanelApplet",
    "#PanelApplet > box",
    "#PanelApplet > widget",
)

HOST_DECLARATIONS = ("background-color: transparent",
                     "background-image: none",
                     "border-color: transparent",
                     "box-shadow: none")

# Themes that already shipped this rule before issue #387 was scoped.
ALREADY_INHERITING = ("Spaced-Win7", "Spaced-Win7Aero-Dark", "Spaced-Ubuntu")

HEX_PATTERN = re.compile(r"#[0-9a-fA-F]{3,8}\b")


def css_rules(css):
    """Return (selectors, declarations) pairs for a flat GTK stylesheet."""
    css = re.sub(r"/\*.*?\*/", " ", css, flags=re.S)
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        selectors = re.sub(r"\s+", " ", match.group(1)).strip()
        yield selectors, re.sub(r"\s+", " ", match.group(2)).strip()


def rule_tokens(selectors):
    return [token.strip() for token in selectors.split(",") if token.strip()]


def host_rules(css):
    """Rules that clear the whole out-of-process applet host selector list."""
    for selectors, declarations in css_rules(css):
        tokens = rule_tokens(selectors)
        if all(host in tokens for host in HOST_SELECTORS):
            yield tokens, declarations


def normalize_hex(color):
    color = color.lower()
    if len(color) == 4:  # #rgb expands to #rrggbb
        return "#" + "".join(char * 2 for char in color[1:])
    return color


class PanelAppletSurfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.themes = json.loads(REGISTRY.read_text(encoding="utf-8"))["themes"]

    def css_for(self, gtk_theme):
        return (THEME_ROOT / gtk_theme / "gtk-3.0/gtk.css").read_text(
            encoding="utf-8")

    def test_every_registry_theme_clears_the_applet_hosts(self):
        for theme in self.themes:
            css = self.css_for(theme["gtk_theme"])
            rules = list(host_rules(css))
            with self.subTest(theme=theme["id"]):
                self.assertTrue(
                    rules,
                    "applet hosts are painted, so Menu/clock/volume/"
                    "show-desktop cannot inherit the panel background")
                for tokens, declarations in rules:
                    for declaration in HOST_DECLARATIONS:
                        self.assertIn(declaration, declarations)

    def test_host_rule_names_every_out_of_process_applet_host(self):
        for theme in self.themes:
            tokens = {token for rule in host_rules(self.css_for(theme["gtk_theme"]))
                      for token in rule[0]}
            with self.subTest(theme=theme["id"]):
                for host in HOST_SELECTORS:
                    self.assertIn(host, tokens, f"{host} can still paint a rectangle")

    def test_host_rules_reuse_the_theme_colour_and_add_no_new_hex(self):
        for theme in self.themes:
            css = self.css_for(theme["gtk_theme"])
            defined = {normalize_hex(value)
                       for value in re.findall(
                           r"@define-color\s+\w+\s+(#[0-9a-fA-F]{3,8})", css)}
            with self.subTest(theme=theme["id"]):
                for tokens, declarations in host_rules(css):
                    color = re.search(r"(^|;)\s*color:\s*([^;]+)", declarations)
                    self.assertIsNotNone(
                        color, "applet labels lose the theme's text colour")
                    value = color.group(2).strip()
                    if value.startswith("@"):
                        self.assertNotIn(" ", value, "applet text colour "
                                         "must be one theme colour token")
                    else:
                        self.assertIn(normalize_hex(value), defined,
                                      "applet text must reuse a colour the "
                                      "theme already defines")
                    for hex_value in HEX_PATTERN.findall(declarations):
                        self.assertIn(
                            normalize_hex(hex_value), defined,
                            f"{hex_value} is a hard-coded colour the theme "
                            f"does not define")

    def test_panel_surface_fill_stays_opaque_behind_the_hosts(self):
        for theme in self.themes:
            css = self.css_for(theme["gtk_theme"])
            fills = []
            for selectors, declarations in css_rules(css):
                tokens = rule_tokens(selectors)
                # The applet host rule clears its hosts; it is not the panel.
                if all(host in tokens for host in HOST_SELECTORS):
                    continue
                if not any(token.startswith(".mate-panel") for token in tokens):
                    continue
                background = re.search(r"background-color:\s*([^;]+)",
                                       declarations)
                if background:
                    fills.append(background.group(1).strip())
            with self.subTest(theme=theme["id"]):
                self.assertTrue(fills, "the theme no longer fills .mate-panel")
                self.assertNotIn("transparent", fills,
                                 "the panel surface itself became transparent")

    def host_rule_tokens(self, css):
        return {token for rule in host_rules(css) for token in rule[0]}

    def test_applet_button_theming_survives_the_transparent_hosts(self):
        # Only the host surfaces clear; the applet buttons keep their own
        # surfaces, so no button selector may join the transparent rule.
        for theme in self.themes:
            with self.subTest(theme=theme["id"]):
                for token in self.host_rule_tokens(self.css_for(theme["gtk_theme"])):
                    self.assertNotIn("button", token)
        for gtk_theme, marker in (("Spaced-WinXP", "#PanelApplet button.brisk-button"),
                                  ("Spaced-WinXP", "button.brisk-button"),
                                  ("Spaced-Geoworks", "#PanelApplet button"),
                                  ("Spaced-Ubuntu", "#PanelPlug button"),
                                  ("Spaced-Win7", "#PanelPlug button"),
                                  ("Spaced-Win7Aero-Dark", "#PanelPlug button")):
            with self.subTest(theme=gtk_theme, marker=marker):
                self.assertIn(marker, self.css_for(gtk_theme))

    def test_themes_that_already_inherited_keep_their_rule(self):
        for gtk_theme in ALREADY_INHERITING:
            with self.subTest(theme=gtk_theme):
                self.assertTrue(list(host_rules(self.css_for(gtk_theme))))
                self.assertIn("#PanelPlug", self.css_for(gtk_theme))

    def test_registry_covers_thirteen_themes(self):
        self.assertEqual(13, len(self.themes))
        self.assertEqual(13, len({theme["gtk_theme"] for theme in self.themes}))


if __name__ == "__main__":
    unittest.main()
