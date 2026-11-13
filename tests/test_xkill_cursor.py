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

    def test_cursor_has_all_sizes_with_centered_hotspots(self):
        data = CURSOR.read_bytes()
        self.assertEqual(b"Xcur", data[:4], "the xkill cursor is not an XCUR file")
        _header, _version, ntoc = struct.unpack_from("<III", data, 4)
        self.assertEqual(ntoc, 4)
        frames = {}
        for index in range(ntoc):
            chunk_type, nominal_size, position = struct.unpack_from(
                "<III", data, 16 + index * 12)
            self.assertEqual(chunk_type, 0xfffd0002)
            (header, image_type, subtype, version, width, height,
             xhot, yhot, delay) = struct.unpack_from("<IIIIIIIII", data, position)
            self.assertGreaterEqual(header, 36)
            self.assertEqual(image_type, chunk_type)
            self.assertEqual(subtype, nominal_size)
            self.assertEqual(version, 1)
            self.assertEqual(delay, 50)
            frames[nominal_size] = (width, height, xhot, yhot)
        self.assertEqual(frames, {
            24: (24, 24, 12, 12),
            32: (32, 32, 16, 16),
            48: (48, 48, 24, 24),
            64: (64, 64, 32, 32),
        })

    def test_build_uses_maintained_svg_source(self):
        source = ROOT / "branding/cursors/xkillcursor.svg"
        script = (ROOT / "branding/cursors/build-xkill-cursor.sh").read_text(
            encoding="utf-8")
        self.assertTrue(source.is_file())
        self.assertIn("Cursor hotspot: 32,32", source.read_text(encoding="utf-8"))
        self.assertIn("source_svg=branding/cursors/xkillcursor.svg", script)
        self.assertIn("rsvg-convert", script)


if __name__ == "__main__":
    unittest.main()
