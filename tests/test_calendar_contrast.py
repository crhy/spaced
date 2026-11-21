"""Resolve real GTK calendar selection colors on an isolated X server."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('xvfb-run') and importlib.util.find_spec('gi'),
                     'requires GTK introspection and Xvfb')
class CalendarContrastTests(unittest.TestCase):
    def test_selected_date_in_every_theme(self):
        probe = r'''
import json, math, re, sys
from pathlib import Path
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
root = Path(sys.argv[1]) / 'overlays/usr/share'
themes = json.loads((root / 'spaced-themes/themes.json').read_text())['themes']
def luminance(color):
    values = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4
              for v in (color.red, color.green, color.blue)]
    return sum(a * b for a, b in zip(values, (.2126, .7152, .0722)))
for theme in themes:
    provider = Gtk.CssProvider()
    provider.load_from_path(str(root / 'themes' / theme['gtk_theme'] / 'gtk-3.0/gtk.css'))
    calendar = Gtk.Calendar()
    context = calendar.get_style_context()
    context.add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)
    for extra in (Gtk.StateFlags.NORMAL, Gtk.StateFlags.FOCUSED,
                  Gtk.StateFlags.BACKDROP, Gtk.StateFlags.FOCUSED | Gtk.StateFlags.BACKDROP):
        state = Gtk.StateFlags.SELECTED | extra
        fg, bg = context.get_color(state), context.get_background_color(state)
        light, dark = sorted((luminance(fg), luminance(bg)), reverse=True)
        ratio = (light + .05) / (dark + .05)
        assert bg.alpha == 1 and ratio >= 4.5, (theme['id'], str(state), fg.to_string(), bg.to_string(), ratio)
    calendar.destroy()
'''
        result = subprocess.run(['xvfb-run', '-a', sys.executable, '-c', probe, str(ROOT)],
                                capture_output=True, text=True, timeout=45)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
