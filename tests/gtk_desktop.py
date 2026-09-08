#!/usr/bin/env python3
"""Render-engine checks; run under xvfb-run with distro python3-gi/GTK3."""
import unittest
from pathlib import Path
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
ROOT = Path(__file__).resolve().parents[1]


def style(provider, nodes):
    path = Gtk.WidgetPath()
    for name, classes in nodes:
        index = path.append_type(Gtk.Widget)
        path.iter_set_object_name(index, name)
        for klass in classes:
            path.iter_add_class(index, klass)
    context = Gtk.StyleContext()
    context.set_path(path)
    context.add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    return context


class DesktopStyleTests(unittest.TestCase):
    def test_selection_and_rubberbands_across_all_palettes(self):
        for css in sorted((ROOT / 'overlays/usr/share/themes').glob('Spaced-*/gtk-3.0/gtk.css')):
            with self.subTest(theme=css.parents[1].name):
                provider = Gtk.CssProvider()
                provider.load_from_path(str(css))
                text = style(provider, [('textview', []), ('text', [])])
                self.assertGreaterEqual(text.get_padding(Gtk.StateFlags.NORMAL).top, 6)
                self.assertGreaterEqual(text.get_padding(Gtk.StateFlags.NORMAL).left, 6)
                selected = style(provider, [('textview', []), ('text', []), ('selection', [])])
                expected = selected.lookup_color('theme_selected_bg_color')[1]
                actual = selected.get_property('background-color', Gtk.StateFlags.NORMAL)
                self.assertEqual(actual.to_string(), expected.to_string())
                for nodes in ([('window', ['background', 'rubberband'])],
                              [('window', ['caja-navigation-window']), ('widget', ['view', 'rubberband'])],
                              [('iconview', ['view']), ('rubberband', [])]):
                    context = style(provider, nodes)
                    color = context.get_property('background-color', Gtk.StateFlags.NORMAL)
                    self.assertGreater(color.alpha, 0, nodes)
                    self.assertLess(color.alpha, 0.5, nodes)


if __name__ == '__main__':
    unittest.main()
