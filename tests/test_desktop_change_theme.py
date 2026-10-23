"""Exercise the Caja "Change Theme…" desktop menu item without a running desktop."""
import importlib.util
import sys
import types
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "overlays/usr/share/caja-python/extensions/spaced-change-theme.py"
sys.dont_write_bytecode = True


class MenuProvider:
    pass


class MenuItem:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.signals = {}

    def connect(self, signal, callback):
        self.signals[signal] = callback


class GObjectBase:
    def __init__(self):
        pass


def load_extension():
    spec = importlib.util.spec_from_file_location("spaced_change_theme", EXTENSION)
    module = importlib.util.module_from_spec(spec)
    caja = types.SimpleNamespace(MenuProvider=MenuProvider, MenuItem=MenuItem)
    gobject = types.SimpleNamespace(GObject=GObjectBase)
    gi = types.SimpleNamespace()
    repository = types.SimpleNamespace(Caja=caja, GObject=gobject)
    with patch.dict(sys.modules, {"gi": gi, "gi.repository": repository}):
        spec.loader.exec_module(module)
    return module


ext = load_extension()


def folder(uri):
    return types.SimpleNamespace(get_uri=lambda: uri)


class ChangeThemeTests(unittest.TestCase):
    def test_desktop_folder_offers_change_theme(self):
        items = ext.SpacedChangeTheme().get_background_items(
            None, folder("x-caja-desktop:///home/user/Desktop"))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].kwargs["label"], "Change Theme…")

    def test_non_desktop_folder_offers_nothing(self):
        items = ext.SpacedChangeTheme().get_background_items(None, folder("file:///home/x"))
        self.assertEqual(items, [])

    def test_activate_opens_theme_chooser(self):
        items = ext.SpacedChangeTheme().get_background_items(
            None, folder("x-caja-desktop:///home/user/Desktop"))
        item = items[0]
        with patch("subprocess.Popen") as popen:
            item.signals["activate"](item)
            popen.assert_called_once_with(["mate-appearance-properties", "--show-page=theme"])


if __name__ == "__main__":
    unittest.main()
