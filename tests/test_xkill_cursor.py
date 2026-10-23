import unittest
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


if __name__ == "__main__":
    unittest.main()
