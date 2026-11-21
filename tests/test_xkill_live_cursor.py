"""Actual grabbed cursor pixels, under Adwaita, on a disposable X server only."""
import ctypes as C
import ctypes.util
import os
from pathlib import Path
import select
import shutil
import subprocess
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('Xvfb') and Path('/usr/bin/xkill').exists(), 'requires Xvfb and xkill')
class LiveXkillCursor(unittest.TestCase):
    def _red_pixels_while_xkill_runs(self, command):
        read_fd, write_fd = os.pipe()
        server = subprocess.Popen(['Xvfb', '-displayfd', str(write_fd), '-screen', '0', '320x240x24', '-nolisten', 'tcp'], pass_fds=(write_fd,), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        os.close(write_fd)
        self.addCleanup(os.close, read_fd)
        def stop(process):
            if process.poll() is None:
                process.terminate()
            process.communicate(timeout=10)
        self.addCleanup(stop, server)
        self.assertTrue(select.select([read_fd], [], [], 10)[0], 'Xvfb did not start')
        display = ':' + os.read(read_fd, 32).decode().strip()
        env = dict(os.environ, DISPLAY=display, XCURSOR_THEME='Adwaita', XCURSOR_PATH=str(ROOT / 'overlays/usr/share/icons') + ':/usr/share/icons', XCURSOR_SIZE='32')
        x11 = C.CDLL(ctypes.util.find_library('X11'))
        fixes = C.CDLL(ctypes.util.find_library('Xfixes'))
        x11.XOpenDisplay.argtypes = [C.c_char_p]
        x11.XOpenDisplay.restype = C.c_void_p
        connection = x11.XOpenDisplay(display.encode())
        self.assertTrue(connection)
        x11.XCloseDisplay.argtypes = [C.c_void_p]
        self.addCleanup(x11.XCloseDisplay, connection)
        class Cursor(C.Structure):
            _fields_ = [('x', C.c_short), ('y', C.c_short), ('width', C.c_ushort), ('height', C.c_ushort), ('xhot', C.c_ushort), ('yhot', C.c_ushort), ('serial', C.c_ulong), ('pixels', C.POINTER(C.c_ulong)), ('atom', C.c_ulong), ('name', C.c_char_p)]
        fixes.XFixesGetCursorImage.argtypes = [C.c_void_p]
        fixes.XFixesGetCursorImage.restype = C.POINTER(Cursor)
        x11.XFree.argtypes = [C.c_void_p]
        killer = subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(stop, killer)
        red = 0
        for _ in range(50):
            pointer = fixes.XFixesGetCursorImage(connection)
            self.assertTrue(pointer)
            cursor = pointer.contents
            red = sum(1 for i in range(cursor.width * cursor.height) if ((cursor.pixels[i] >> 16) & 255) > 180 and ((cursor.pixels[i] >> 8) & 255) < 100 and (cursor.pixels[i] & 255) < 100)
            x11.XFree(pointer)
            if red > 20:
                break
            time.sleep(.05)
        return red

    def test_adwaita_desktop_still_gets_red_x(self):
        red = self._red_pixels_while_xkill_runs([str(ROOT / 'overlays/usr/local/bin/xkill')])
        self.assertGreater(red, 20, 'xkill grabbed a cursor without the red X')

    def test_direct_usr_bin_xkill_falls_back_to_default_red_x(self):
        # #422 (rhY: never lose the red X again): no wrapper, Adwaita selected - libXcursor falls back to the
        # "default" theme, which ships the same red X, so even /usr/bin/xkill shows it.
        red = self._red_pixels_while_xkill_runs(['/usr/bin/xkill'])
        self.assertGreater(red, 20, 'plain /usr/bin/xkill showed the stock cursor instead of the red X')
