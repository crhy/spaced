import unittest
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / "overlays"
ICONS = OVERLAY / "usr/share/icons"
CURSOR = ICONS / "Spaced-Cursors/cursors/pirate"
INDEX = ICONS / "Spaced-Cursors/index.theme"


class XkillCursorTests(unittest.TestCase):
    def test_cursor_is_xcur_binary(self):
        self.assertTrue(CURSOR.is_file(), "the xkill cursor file is missing")
        self.assertEqual(b"Xcur", CURSOR.read_bytes()[:4],
                         "the xkill cursor is not an XCUR binary file")

    def test_index_inherits_adwaita(self):
        self.assertTrue(INDEX.is_file(), "the cursor theme index is missing")
        self.assertIn("Inherits=Adwaita", INDEX.read_text(encoding="utf-8"),
                      "the cursor theme does not inherit Adwaita")

    def test_highlights_inside_red(self):
        data = CURSOR.read_bytes()
        self.assertEqual(b"Xcur", data[:4], "the xkill cursor is not an XCUR file")
        size = 64
        pixels = data[len(data) - size * size * 4:]
        self.assertEqual(len(pixels), size * size * 4, "no 64 px frame to check")

        def at(x, y):
            i = (y * size + x) * 4
            b, g, r, a = pixels[i:i + 4]
            return (r, g, b, a)

        reds = [(x, y) for y in range(size) for x in range(size)
                if at(x, y)[0] > 150 and at(x, y)[1] < 80]
        bad = [(x, y) for y in range(size) for x in range(size)
               if at(x, y)[0] > 200 and at(x, y)[1] > 200 and at(x, y)[2] > 200
               and at(x, y)[3] > 128
               and not any(abs(x - rx) <= 3 and abs(y - ry) <= 3 for rx, ry in reds)]
        self.assertEqual(bad, [],
                         f"white highlight pixels stick out past the red X: {bad}")


if __name__ == "__main__":
    unittest.main()
