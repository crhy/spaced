import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "overlays/usr/share/caja-python/extensions/spaced-open-terminal.py"
sys.dont_write_bytecode = True


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
        return load(EXTENSION, "spaced_open_terminal_test")


class File:
    def __init__(self, uri):
        self.uri = uri

    def get_uri(self):
        return self.uri


class OpenTerminalMenuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.extension = load_extension()

    def test_single_local_folder_gets_one_action(self):
        with tempfile.TemporaryDirectory() as folder:
            provider = self.extension.SpacedOpenTerminal()
            items = provider.get_file_items(None, [File("file://" + folder)])
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].kwargs["label"], "Open in Terminal Here")
            self.assertEqual(items[0].kwargs["icon"], "utilities-terminal")

    def test_non_folder_multi_and_remote_are_hidden(self):
        provider = self.extension.SpacedOpenTerminal()
        self.assertEqual(
            provider.get_file_items(None, [File("file:///nonexistent-zz/path")]), [])
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(
                provider.get_file_items(None, [File("file://" + folder), File("file://" + folder)]), [])
        self.assertEqual(
            provider.get_file_items(None, [File("sftp://host/home/user/projects")]), [])

    def test_on_activate_launches_found_terminal_at_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            provider = self.extension.SpacedOpenTerminal()
            items = provider.get_file_items(None, [File("file://" + folder)])
            callback, args = items[0].signals["activate"]
            with patch("shutil.which", return_value="/usr/bin/mate-terminal"), \
                    patch("subprocess.Popen") as popen:
                callback(items[0], *args)
                argv = popen.call_args[0][0]
                self.assertEqual(argv[0], "mate-terminal")
                self.assertIn(folder, argv)

    def test_on_activate_without_any_terminal_raises_nothing(self):
        with tempfile.TemporaryDirectory() as folder:
            provider = self.extension.SpacedOpenTerminal()
            items = provider.get_file_items(None, [File("file://" + folder)])
            callback, args = items[0].signals["activate"]
            with patch("shutil.which", return_value=None), \
                    patch("subprocess.Popen") as popen:
                callback(items[0], *args)
                popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
