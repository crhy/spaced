"""The Caja right-click extensions Spaced ships are first-party (issue #302).

Runs without a display: the real python3-caja bindings are exercised by exec'ing
the shipped extension files, and the menu behaviour is exercised against stub
Caja/GObject modules.
"""
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
EXTENSIONS = ROOT / "overlays/usr/share/caja-python/extensions"
OPEN_TERMINAL = EXTENSIONS / "spaced-open-terminal.py"
PACKAGES_YAML = ROOT / "config/packages.yaml"
sys.dont_write_bytecode = True


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _real_caja_available():
    try:
        import gi
        gi.require_version("Caja", "2.0")
        from gi.repository import Caja  # noqa: F401
        return True
    except (ImportError, ValueError):
        return False


def folder(uri):
    return types.SimpleNamespace(get_uri=lambda: uri)


class CajaPackageBoundaryTests(unittest.TestCase):
    """The terminal action left the package set; the rest of Caja stayed put."""

    def test_caja_open_terminal_is_not_installed(self):
        text = PACKAGES_YAML.read_text(encoding="utf-8")
        self.assertNotIn("caja-open-terminal", text)
        groups = yaml.safe_load(text)
        self.assertNotIn("caja-open-terminal", groups.get("file_managers", []))

    def test_caja_itself_stays_installed(self):
        text = PACKAGES_YAML.read_text(encoding="utf-8")
        for package in ("caja", "caja-admin", "python3-caja", "caja-share"):
            self.assertIn(f"- {package}\n", text, f"{package} must stay installed")

    def test_the_extension_is_shipped_by_a_local_package(self):
        builder = (ROOT / "scripts/iso/build-local-packages.sh").read_text(encoding="utf-8")
        self.assertIn("usr/share/caja-python/extensions/spaced-open-terminal.py", builder)


class MenuProvider:
    pass


class MenuItem:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.signals = {}
        self.sensitive = True

    def connect(self, signal, callback, *args):
        self.signals[signal] = (callback, args)

    def set_property(self, name, value):
        assert name == "sensitive"
        self.sensitive = value


class GObjectBase:
    def __init__(self):
        pass


def load_open_terminal():
    """Import the shipped extension with stub gi modules."""
    caja = types.SimpleNamespace(MenuProvider=MenuProvider, MenuItem=MenuItem)
    gobject = types.SimpleNamespace(GObject=GObjectBase)
    with patch.dict(sys.modules, {
        "gi": types.SimpleNamespace(),
        "gi.repository": types.SimpleNamespace(Caja=caja, GObject=gobject),
    }):
        return load(OPEN_TERMINAL, "spaced_open_terminal_stub")


class OpenTerminalMenuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.extension = load_open_terminal()

    def test_local_folder_offers_open_terminal(self):
        provider = self.extension.SpacedOpenTerminal()
        with patch("shutil.which", return_value="/usr/bin/mate-terminal"):
            items = provider.get_file_items(None, [folder(Path(ROOT).as_uri())])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].kwargs["name"], "SpacedOpenTerminal::open")
        self.assertIn("terminal", items[0].kwargs["label"].lower())
        self.assertTrue(items[0].sensitive)

    def test_files_and_remote_folders_offer_nothing(self):
        provider = self.extension.SpacedOpenTerminal()
        with patch("shutil.which", return_value="/usr/bin/mate-terminal"):
            self.assertEqual(provider.get_file_items(None, [folder("file:///etc/hostname")]), [])
            self.assertEqual(provider.get_file_items(None, [folder("smb://host/share/")]), [])
            self.assertEqual(provider.get_file_items(None, [folder("x-caja-desktop:///")]), [])
            two = [folder(Path(ROOT).as_uri()), folder(Path(ROOT).as_uri())]
            self.assertEqual(provider.get_file_items(None, two), [])

    def test_activate_starts_the_terminal_in_the_folder(self):
        provider = self.extension.SpacedOpenTerminal()
        with patch("shutil.which", return_value="/usr/bin/mate-terminal"), \
                patch("subprocess.Popen") as popen:
            item = provider.get_file_items(None, [folder(Path(ROOT).as_uri())])[0]
            callback, args = item.signals["activate"]
            callback(item, *args)
            popen.assert_called_once_with(["mate-terminal"], cwd=str(ROOT), close_fds=True)

    def test_no_terminal_keeps_the_item_inactive(self):
        provider = self.extension.SpacedOpenTerminal()
        with patch("shutil.which", return_value=None), \
                patch("subprocess.Popen") as popen, \
                patch("subprocess.run") as run:
            item = provider.get_file_items(None, [folder(Path(ROOT).as_uri())])[0]
            self.assertFalse(item.sensitive)
            callback, args = item.signals["activate"]
            callback(item, *args)
            popen.assert_not_called()
            run.assert_not_called()

    def test_a_sandboxed_caller_uses_the_host_terminal(self):
        provider = self.extension.SpacedOpenTerminal()

        def which(name):
            return "/usr/bin/flatpak-spawn" if name == "flatpak-spawn" else None

        with patch("shutil.which", side_effect=which), \
                patch("subprocess.run") as run, \
                patch("subprocess.Popen") as popen:
            run.return_value = types.SimpleNamespace(returncode=0)
            item = provider.get_file_items(None, [folder(Path(ROOT).as_uri())])[0]
            self.assertTrue(item.sensitive)
            callback, args = item.signals["activate"]
            callback(item, *args)
            popen.assert_called_once_with(
                ["flatpak-spawn", "--host", "mate-terminal"], cwd=str(ROOT), close_fds=True)
            self.assertEqual(run.call_args_list[0].args[0],
                             ["flatpak-spawn", "--host", "which", "mate-terminal"])

    def test_mate_terminal_is_preferred_over_the_alternative(self):
        provider = self.extension.SpacedOpenTerminal()
        asked = []

        def which(name):
            asked.append(name)
            return "/usr/bin/" + name

        with patch("shutil.which", side_effect=which), patch("subprocess.Popen") as popen:
            item = provider.get_file_items(None, [folder(Path(ROOT).as_uri())])[0]
            callback, args = item.signals["activate"]
            callback(item, *args)
            popen.assert_called_once_with(["mate-terminal"], cwd=str(ROOT), close_fds=True)
        self.assertEqual(asked[0], "mate-terminal")


@unittest.skipUnless(_real_caja_available(), "python3-caja GObject bindings are not installed")
class RealCajaExtensionTests(unittest.TestCase):
    """The stub modules above cannot catch GObject base-class or property errors."""

    def test_each_first_party_extension_defines_a_menu_provider(self):
        import gi
        gi.require_version("Caja", "2.0")
        from gi.repository import Caja
        for path in sorted(EXTENSIONS.glob("*.py")):
            with self.subTest(extension=path.name):
                module = load(path, "spaced_" + path.stem.replace("-", "_") + "_real")
                providers = [value for value in vars(module).values()
                             if isinstance(value, type) and issubclass(value, Caja.MenuProvider)]
                self.assertTrue(providers, f"{path.name} defines no Caja.MenuProvider")

    def test_open_terminal_labels_a_terminal(self):
        import gi
        gi.require_version("Caja", "2.0")
        from gi.repository import Caja
        module = load(OPEN_TERMINAL, "spaced_open_terminal_real")
        self.assertTrue(issubclass(module.SpacedOpenTerminal, Caja.MenuProvider))
        provider = module.SpacedOpenTerminal()
        items = provider.get_file_items(None, [folder(Path(ROOT).as_uri())])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].props.name, "SpacedOpenTerminal::open")
        self.assertIn("terminal", items[0].props.label.lower())


if __name__ == "__main__":
    unittest.main()
