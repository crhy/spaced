#!/usr/bin/env python3
"""Render-engine checks; run under xvfb-run with distro python3-gi/GTK3."""
import unittest
import time
from pathlib import Path
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk
try:
    gi.require_version('GtkSource', '4')
    from gi.repository import GtkSource
except ValueError:
    GtkSource = None
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
    @unittest.skipIf(GtkSource is None, 'requires gir1.2-gtksource-4 (Pluma)')
    def test_pluma_caret_renders_across_all_palettes(self):
        def settle(duration=0.1):
            deadline = time.monotonic() + duration
            while time.monotonic() < deadline:
                while Gtk.events_pending():
                    Gtk.main_iteration()
                time.sleep(0.01)

        settings = Gtk.Settings.get_default()
        original = settings.get_property('gtk-cursor-blink')
        self.addCleanup(settings.set_property, 'gtk-cursor-blink', original)
        settings.set_property('gtk-cursor-blink', False)
        window = Gtk.Window()
        self.addCleanup(window.destroy)
        window.set_default_size(400, 200)
        view = GtkSource.View()
        buffer = view.get_buffer()
        buffer.set_text('Cursor test\n')
        buffer.place_cursor(buffer.get_start_iter())
        buffer.set_style_scheme(GtkSource.StyleSchemeManager.get_default().get_scheme('classic'))
        window.add(view)
        window.show_all()
        window.get_window().focus(Gdk.CURRENT_TIME)
        view.grab_focus()
        settle()
        self.assertTrue(view.has_focus())
        self.assertTrue(window.is_active())

        def pixels():
            return Gdk.pixbuf_get_from_window(window.get_window(), 0, 0, 400, 200).get_pixels()

        for css in sorted((ROOT / 'overlays/usr/share/themes').glob('Spaced-*/gtk-3.0/gtk.css')):
            with self.subTest(theme=css.parents[1].name):
                provider = Gtk.CssProvider()
                provider.load_from_path(str(css))
                screen = Gdk.Screen.get_default()
                Gtk.StyleContext.add_provider_for_screen(screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_THEME)
                try:
                    view.set_cursor_visible(False)
                    settle()
                    hidden = pixels()
                    view.set_cursor_visible(True)
                    settle()
                    visible = pixels()
                    self.assertNotEqual(hidden, visible, 'caret is not drawn')
                finally:
                    Gtk.StyleContext.remove_provider_for_screen(screen, provider)

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
