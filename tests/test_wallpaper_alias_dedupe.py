"""Issue #443: the MATE picker saved wallpapers under their .png alias paths,
so every Spaced wallpaper shows twice in Appearance > Background (the picker's
own entry plus the catalog's .jpg entry). The login migration must rewrite the
current selection to the .jpg and drop only the four alias entries, never a
user wallpaper outside /usr/share/backgrounds/spaced."""
import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys_path = ROOT / "overlays/usr/lib/spaced-linux/migrate-desktop.py"

spec = importlib.util.spec_from_file_location("migration", sys_path)
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)

SPACED = "/usr/share/backgrounds/spaced"

HEADER = ('<?xml version="1.0"?>\n'
          '<!DOCTYPE wallpapers SYSTEM "mate-wp-list.dtd">\n'
          '<wallpapers>\n')


def entry(filename, name=None):
    return ('  <wallpaper deleted="false">\n'
            f'    <name>{name or filename.rsplit("/", 1)[-1]}</name>\n'
            f'    <filename>{filename}</filename>\n'
            '    <options>zoom</options>\n'
            '    <shade_type>solid</shade_type>\n'
            '    <pcolor>rgb(5,9,18)</pcolor>\n'
            '    <scolor>rgb(5,9,18)</scolor>\n'
            '    <artist>(none)</artist>\n'
            '  </wallpaper>\n')


def wp_list(*filenames):
    return HEADER + "".join(entry(f) for f in filenames) + "</wallpapers>\n"


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = Path(self.temp.name) / "config"
        self.backgrounds = self.config / "mate/backgrounds.xml"
        self.set_calls = []
        migration.get_picture_filename = lambda: self.picture
        migration.set_picture_filename = self.set_calls.append
        self.picture = None

    def write_backgrounds(self, text):
        self.backgrounds.parent.mkdir(parents=True, exist_ok=True)
        self.backgrounds.write_text(text, encoding="utf-8")

    def test_alias_and_jpg_entries_end_with_only_the_jpg(self):
        self.write_backgrounds(wp_list(
            f"{SPACED}/spaced-orbit-4k.png",
            f"{SPACED}/spaced-orbit-4k.jpg",
            f"{SPACED}/euclid-galaxy-garland.png",
            f"{SPACED}/euclid-galaxy-garland.jpg",
        ))
        migration.migrate_wallpaper_aliases(self.config)
        text = self.backgrounds.read_text(encoding="utf-8")
        self.assertNotIn(f"{SPACED}/spaced-orbit-4k.png", text)
        self.assertNotIn(f"{SPACED}/euclid-galaxy-garland.png", text)
        self.assertIn(f"{SPACED}/spaced-orbit-4k.jpg", text)
        self.assertIn(f"{SPACED}/euclid-galaxy-garland.jpg", text)

    def test_running_twice_changes_nothing(self):
        self.write_backgrounds(wp_list(
            f"{SPACED}/spaced-orbit-4k.png",
            f"{SPACED}/spaced-orbit-4k.jpg",
        ))
        migration.migrate_wallpaper_aliases(self.config)
        once = self.backgrounds.read_text(encoding="utf-8")
        migration.migrate_wallpaper_aliases(self.config)
        self.assertEqual(self.backgrounds.read_text(encoding="utf-8"), once)

    def test_a_user_wallpaper_is_never_touched(self):
        personal = "/home/rhy/.local/share/backgrounds/spaced/ubuntu.jpg"
        self.write_backgrounds(wp_list(
            f"{SPACED}/spaced-orbit-4k.png",
            f"{SPACED}/spaced-orbit-4k.jpg",
            personal,
            f"{SPACED}/SimpleBackb.png",
        ))
        migration.migrate_wallpaper_aliases(self.config)
        text = self.backgrounds.read_text(encoding="utf-8")
        self.assertIn(personal, text)
        # SimpleBackb.png is a real file, not one of the four aliases.
        self.assertIn(f"{SPACED}/SimpleBackb.png", text)

    def test_an_alias_without_its_jpg_entry_is_kept(self):
        self.write_backgrounds(wp_list(f"{SPACED}/SpacedBack.png"))
        migration.migrate_wallpaper_aliases(self.config)
        text = self.backgrounds.read_text(encoding="utf-8")
        self.assertIn(f"{SPACED}/SpacedBack.png", text)

    def test_the_current_selection_moves_from_the_alias_to_the_jpg(self):
        self.picture = f"{SPACED}/spaced-orbit-4k.png"
        migration.migrate_wallpaper_aliases(self.config)
        self.assertEqual(self.set_calls, [f"{SPACED}/spaced-orbit-4k.jpg"])

    def test_a_selection_outside_the_aliases_is_left_alone(self):
        for picture in (None, f"{SPACED}/spaced-orbit-4k.jpg",
                        "/home/rhy/Pictures/tunnel.png", ""):
            self.picture = picture
            migration.migrate_wallpaper_aliases(self.config)
        self.assertEqual(self.set_calls, [])


if __name__ == "__main__":
    unittest.main()
