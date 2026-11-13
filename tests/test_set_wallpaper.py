import contextlib
import importlib.machinery
import importlib.util
import io
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "overlays/usr/lib/spaced-linux/spaced_wallpaper.py"
EXTENSION = ROOT / "overlays/usr/share/caja-python/extensions/spaced-set-wallpaper.py"
DIALOG = ROOT / "overlays/usr/lib/spaced-linux/spaced-wallpaper-dialog"
sys.dont_write_bytecode = True


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


wallpaper = load(HELPER, "spaced_wallpaper_test")


class WallpaperHelperTests(unittest.TestCase):
    def test_similar_ratio_fills_and_different_ratio_fits(self):
        self.assertEqual(wallpaper.default_style(1920, 1080, 1920, 1080), "zoom")
        self.assertEqual(wallpaper.default_style(1080, 1920, 1920, 1080), "scaled")
        self.assertEqual(wallpaper.default_style(0, 1080, 1920, 1080), "scaled")

    def test_copy_preserves_original_and_never_overwrites_collision(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pictures = root / "Pictures"
            source_a = root / "a" / "photo.jpg"
            source_b = root / "b" / "photo.jpg"
            source_a.parent.mkdir()
            source_b.parent.mkdir()
            source_a.write_bytes(b"first")
            source_b.write_bytes(b"second")
            first = Path(wallpaper.copy_to_wallpapers(source_a, pictures))
            second = Path(wallpaper.copy_to_wallpapers(source_b, pictures))
            self.assertEqual(first.read_bytes(), b"first")
            self.assertEqual(second.read_bytes(), b"second")
            self.assertNotEqual(first, second)
            self.assertEqual(wallpaper.copy_to_wallpapers(source_a, pictures), str(first))


class MenuProvider:
    pass


class MenuItem:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.signals = {}

    def connect(self, signal, callback, *args):
        self.signals[signal] = (callback, args)


class GObjectBase:
    def __init__(self):
        pass


def load_extension():
    caja = types.SimpleNamespace(MenuProvider=MenuProvider, MenuItem=MenuItem)
    gobject = types.SimpleNamespace(GObject=GObjectBase)
    with patch.dict(sys.modules, {
        "gi": types.SimpleNamespace(),
        "gi.repository": types.SimpleNamespace(Caja=caja, GObject=gobject),
    }):
        return load(EXTENSION, "spaced_set_wallpaper_test")


def load_dialog():
    """Import the GTK dialog script with stub gi/spaced_wallpaper modules."""
    gi = types.SimpleNamespace(require_version=lambda *args: None)
    repository = types.SimpleNamespace(
        Gdk=types.SimpleNamespace(),
        GdkPixbuf=types.SimpleNamespace(),
        Gio=types.SimpleNamespace(),
        GLib=types.SimpleNamespace(),
        Gtk=types.SimpleNamespace(),
    )
    gi.repository = repository
    wallpaper_module = types.SimpleNamespace(
        copy_to_wallpapers=lambda *args: None, default_style=lambda *args: None,
    )
    name = "spaced_wallpaper_dialog_test"
    spec = importlib.util.spec_from_file_location(
        name, str(DIALOG), loader=importlib.machinery.SourceFileLoader(name, str(DIALOG)))
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {
        "gi": gi,
        "gi.repository": repository,
        "spaced_wallpaper": wallpaper_module,
    }):
        spec.loader.exec_module(module)
    return module


class File:
    def __init__(self, uri, mime="image/jpeg"):
        self.uri = uri
        self.mime = mime

    def get_uri(self):
        return self.uri

    def get_mime_type(self):
        return self.mime


class WallpaperMenuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.extension = load_extension()

    def test_one_local_image_gets_action(self):
        items = self.extension.SpacedSetWallpaper().get_file_items(
            None, [File("file:///home/user/My%20Photo.jpg")])
        self.assertEqual(items[0].kwargs["label"], "Set as Wallpaper…")
        callback, args = items[0].signals["activate"]
        with patch("subprocess.Popen") as popen:
            callback(items[0], *args)
            popen.assert_called_once_with(
                ["/usr/lib/spaced-linux/spaced-wallpaper-dialog", "/home/user/My Photo.jpg"],
                close_fds=True,
            )

    def test_remote_non_image_and_multiple_files_are_hidden(self):
        provider = self.extension.SpacedSetWallpaper()
        self.assertEqual(provider.get_file_items(None, [File("smb://host/photo.jpg")]), [])
        self.assertEqual(provider.get_file_items(None, [File("file:///tmp/a.txt", "text/plain")]), [])
        self.assertEqual(provider.get_file_items(None, [File("file:///tmp/a.jpg", None)]), [])
        self.assertEqual(provider.get_file_items(None, [File("file:///tmp/a.jpg"), File("file:///tmp/b.jpg")]), [])


USAGE_LINE = "usage: spaced-wallpaper-dialog ABSOLUTE-IMAGE-PATH"


class WallpaperDialogUsageTests(unittest.TestCase):
    """A bad command line must explain itself instead of exiting 2 silently."""

    @classmethod
    def setUpClass(cls):
        cls.dialog = load_dialog()

    def run_main(self, *args):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            status = self.dialog.main(["spaced-wallpaper-dialog", *args])
        return status, stderr.getvalue()

    def test_no_argument_prints_one_usage_line(self):
        status, stderr = self.run_main()
        self.assertEqual(status, 2)
        self.assertEqual(stderr.splitlines(), [USAGE_LINE])

    def test_relative_path_prints_one_usage_line(self):
        status, stderr = self.run_main("Pictures/photo.jpg")
        self.assertEqual(status, 2)
        self.assertEqual(stderr.splitlines(), [USAGE_LINE])

    def test_extra_argument_prints_one_usage_line(self):
        status, stderr = self.run_main("/home/user/photo.jpg", "extra")
        self.assertEqual(status, 2)
        self.assertEqual(stderr.splitlines(), [USAGE_LINE])


if __name__ == "__main__":
    unittest.main()
