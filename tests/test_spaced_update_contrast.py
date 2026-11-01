"""Header subtitle legibility of Spaced Update on every Spaced theme.

The header bar paints its own surface (light bars in Win7, Win11-Light,
MacOS...; dark bars elsewhere), so a subtitle coloured from the *window*
foreground lands on the bar with almost no contrast.  These checks render the
real window headless, one subprocess per theme, and measure the WCAG contrast
ratio between the subtitle pixels and the bar behind them.
"""
from pathlib import Path
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True

APP = ROOT / 'overlays/usr/lib/spaced-linux/spaced-update.py'
INSTALLED_THEMES_JSON = Path('/usr/share/spaced-themes/themes.json')
THEMES_JSON = (INSTALLED_THEMES_JSON
               if INSTALLED_THEMES_JSON.is_file()
               else ROOT / 'overlays/usr/share/spaced-themes/themes.json')
MIN_RATIO = 4.5
SUBTITLE_TEXT = 'System and application updates \u00b7 0.2.6'

CAPTURE_SOURCE = '''"""Render Spaced Update's header bar and dump it as a PPM image."""
import os
import sys
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib
import importlib.util

spec = importlib.util.spec_from_file_location('spaced_update_app',
                                              os.environ['SPACED_UPDATE_APP'])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

app = module.App()
header = app.get_titlebar()
# Leave only the subtitle in the bar: the title and the icon buttons have
# their own colours and would pollute the measurement.
header.set_title('')
header.set_subtitle(os.environ['SPACED_CONTRAST_SUBTITLE'])
header.set_show_close_button(False)
for child in list(header.get_children()):
    header.remove(child)
app.show_all()
for _ in range(25):
    while Gtk.events_pending():
        Gtk.main_iteration()
    GLib.usleep(25000)

alloc = header.get_allocation()
pixbuf = Gdk.pixbuf_get_from_window(app.get_window(), alloc.x, alloc.y,
                                    alloc.width, alloc.height)
width = pixbuf.get_width()
height = pixbuf.get_height()
channels = pixbuf.get_n_channels()
stride = pixbuf.get_rowstride()
raw = pixbuf.get_pixels()
rows = bytearray()
for y in range(height):
    row = raw[y * stride:y * stride + width * channels]
    rows += b''.join(row[x:x + 3] for x in range(0, len(row), channels))
with open(sys.argv[1], 'wb') as handle:
    handle.write(b'P6\\n%d %d\\n255\\n' % (width, height))
    handle.write(bytes(rows))
'''


def read_ppm(path):
    with open(path, 'rb') as handle:
        handle.readline()
        width, height = map(int, handle.readline().split())
        handle.readline()
        data = handle.read()
    stride = width * 3
    return width, height, [data[y * stride:(y + 1) * stride] for y in range(height)]


def _channel_luminance(value):
    scaled = value / 255.0
    if scaled <= 0.03924:
        return scaled / 12.92
    return ((scaled + 0.055) ** 2.4) / 1.055


def relative_luminance(pixel):
    return (0.212276 * _channel_luminance(pixel[0])
            + 0.71522 * _channel_luminance(pixel[1])
            + 0.072286 * _channel_luminance(pixel[2]))


def contrast_ratio(first, second):
    bright, dark = sorted((relative_luminance(first), relative_luminance(second)),
                          reverse=True)
    return (bright + 0.05) / (dark + 0.05)


def measure(path):
    """Background = most common colour of the subtitle band, text = the
    pixel farthest from it."""
    width, height, rows = read_ppm(path)
    band = [row[x * 3:x * 3 + 3]
            for row in rows[height // 2:height - 4]
            for x in range(8, width - 8)]
    if not band:
        raise AssertionError('subtitle band is empty in %s' % path)
    counts = {}
    for pixel in band:
        counts[pixel] = counts.get(pixel, 0) + 1
    background = max(counts, key=counts.get)
    text = max(band, key=lambda pixel: contrast_ratio(pixel, background))
    return background, text, contrast_ratio(text, background)


@unittest.skipIf(shutil.which('xvfb-run') is None, 'needs xvfb-run')
@unittest.skipIf(not Path('/usr/share/themes/Spaced-Mint').is_dir(),
                 'needs the Spaced themes installed (CI)')
@unittest.skipIf(not APP.is_file(), 'needs spaced-update.py')
@unittest.skipIf(not THEMES_JSON.is_file(), 'needs themes.json')
class HeaderSubtitleContrastTests(unittest.TestCase):
    def _themes(self):
        return [entry['gtk_theme']
                for entry in json.loads(THEMES_JSON.read_text())['themes']]

    def _capture(self, gtk_theme, workdir):
        script = workdir / 'capture_header.py'
        script.write_text(CAPTURE_SOURCE)
        image = workdir / ('header-%s.ppm' % gtk_theme)
        env = dict(os.environ,
                   GTK_THEME=gtk_theme,
                   SPACED_UPDATE_APP=str(APP),
                   SPACED_UPDATE_NO_AUTOCHECK='1',
                   SPACED_CONTRAST_SUBTITLE=SUBTITLE_TEXT)
        result = subprocess.run(['xvfb-run', '-a', 'python3', str(script), str(image)],
                                env=env, timeout=60, capture_output=True)
        self.assertEqual(result.returncode, 0,
                         'rendering %s failed: %s' % (gtk_theme, result.stderr.decode()))
        return image

    def test_header_subtitle_stays_readable_on_every_theme(self):
        workdir = Path(tempfile.mkdtemp(prefix='contrast-',
                                        dir=str(ROOT / 'build')
                                        if (ROOT / 'build').is_dir() else None))
        self.addCleanup(shutil.rmtree, workdir, True)
        table = []
        for gtk_theme in self._themes():
            background, text, ratio = measure(str(self._capture(gtk_theme, workdir)))
            table.append((gtk_theme, background, text, ratio))
        print('\nheader subtitle contrast (Spaced Update):')
        for gtk_theme, background, text, ratio in table:
            print('  %-22s #%02x%02x%02x on #%02x%02x%02x -> %.2f'
                  % (gtk_theme, text[0], text[1], text[2],
                     background[0], background[1], background[2], ratio))
        for gtk_theme, background, text, ratio in table:
            with self.subTest(theme=gtk_theme):
                self.assertGreaterEqual(
                    ratio, MIN_RATIO,
                    'subtitle text #%02x%02x%02x on header #%02x%02x%02x is '
                    'unreadable in %s (contrast %.2f < %.1f)'
                    % (text[0], text[1], text[2], background[0], background[1],
                       background[2], gtk_theme, ratio, MIN_RATIO))

    def _css_blocks(self):
        source = APP.read_text()
        start = source.index('APP_CSS = b"""') + len('APP_CSS = b"""')
        css = source[start:source.index('"""', start)]
        blocks = []
        for chunk in css.split('}'):
            if '{' not in chunk:
                continue
            selector, body = chunk.split('{', 1)
            blocks.append((re.sub(r'\s+', ' ', selector).strip(), '{' + body))
        return blocks

    def _text_colours(self, body):
        """Only the `color:` property, never background-color/border-color."""
        return [match.group(1).strip()
                for match in re.finditer(r'[;{]\s*color:\s*([^;]+)', body)]

    def test_header_subtitle_is_dimmed_not_recoloured(self):
        blocks = {selector: body
                  for selector, body in self._css_blocks()
                  if 'headerbar .subtitle' in selector}
        self.assertTrue(blocks, 'no headerbar .subtitle rule')
        for selector, body in blocks.items():
            self.assertNotIn('color:', body,
                             'the header subtitle must inherit the bar\'s own '
                             'text colour (%s)' % selector)
            self.assertRegex(body, r'opacity:',
                             'the header subtitle must be dimmed with opacity '
                             '(%s)' % selector)

    def test_header_text_never_borrows_the_window_foreground_as_an_alpha(self):
        offenders = []
        for selector, body in self._css_blocks():
            if 'headerbar' not in selector and 'titlebar' not in selector:
                continue
            for colour in self._text_colours(body):
                if 'alpha(' in colour and 'theme_fg_color' in colour:
                    offenders.append('%s -> %s' % (selector, colour))
        self.assertEqual(offenders, [],
                         'header text must not be an alpha of @theme_fg_color: '
                         + ', '.join(offenders))

    def test_body_subtitle_keeps_the_window_foreground(self):
        blocks = {selector: body
                  for selector, body in self._css_blocks()
                  if '.spaced-subtitle' in selector}
        self.assertTrue(blocks, 'no .spaced-subtitle rule')
        for selector, body in blocks.items():
            colours = self._text_colours(body)
            self.assertTrue(colours,
                            'labels on the window background must state '
                            '@theme_fg_color explicitly (%s)' % selector)
            for colour in colours:
                self.assertEqual(colour, '@theme_fg_color',
                                 '%s colours body text with %s' % (selector, colour))

    def test_text_on_the_selection_surface_uses_the_matching_foreground(self):
        offenders = []
        for selector, body in self._css_blocks():
            if 'background-color: @theme_selected_bg_color' not in body:
                continue
            for colour in self._text_colours(body):
                if 'selected_fg' not in colour:
                    offenders.append('%s -> %s' % (selector, colour))
        self.assertEqual(offenders, [],
                         'text on @theme_selected_bg_color must use '
                         '@theme_selected_fg_color: '
                         + ', '.join(offenders))


if __name__ == '__main__':
    unittest.main()
