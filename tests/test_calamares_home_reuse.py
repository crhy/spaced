"""Regression coverage for GitHub issue #413."""

import importlib.util
from pathlib import Path
import sys
import tempfile
import types
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_DIR = ROOT / "overlays/etc/calamares/modules/spacedfstabguard"
SETTINGS = ROOT / "overlays/etc/calamares/settings.conf"


class Storage:
    def __init__(self, values):
        self.values = values

    def value(self, key):
        return self.values.get(key)


def load_guard(values):
    fake = types.SimpleNamespace(
        globalstorage=Storage(values),
        utils=types.SimpleNamespace(warning=lambda _message: None, debug=lambda _message: None),
    )
    old = sys.modules.get("libcalamares")
    sys.modules["libcalamares"] = fake
    try:
        spec = importlib.util.spec_from_file_location("spacedfstabguard", MODULE_DIR / "main.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if old is None:
            del sys.modules["libcalamares"]
        else:
            sys.modules["libcalamares"] = old


class HomeReuseGuardTests(unittest.TestCase):
    def run_guard(self, partitions, reuse=False, initial="# fstab\n"):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        etc = Path(temp.name) / "etc"
        etc.mkdir()
        fstab = etc / "fstab"
        fstab.write_text(initial, encoding="utf-8")
        guard = load_guard({
            "partitions": partitions,
            "reuseHome": reuse,
            "rootMountPoint": temp.name,
        })
        return guard.run(), fstab

    def test_missing_reused_home_stops_install(self):
        result, _fstab = self.run_guard([], reuse=True)
        self.assertIsInstance(result, tuple)
        self.assertIn("final partition plan lost it", result[1])

    def test_unselected_home_needs_no_entry(self):
        result, fstab = self.run_guard([], reuse=False)
        self.assertIsNone(result)
        self.assertEqual(fstab.read_text(encoding="utf-8"), "# fstab\n")

    def test_existing_home_entry_is_preserved(self):
        original = "UUID=old /home ext4 defaults,noatime 0 2\n"
        result, fstab = self.run_guard(
            [{"mountPoint": "/home", "fs": "ext4", "uuid": "old"}],
            reuse=True,
            initial=original,
        )
        self.assertIsNone(result)
        self.assertEqual(fstab.read_text(encoding="utf-8"), original)

    def test_missing_home_entry_is_repaired_by_uuid(self):
        result, fstab = self.run_guard(
            [{"mountPoint": "/home", "fs": "ext4", "uuid": "home-uuid"}],
            reuse=True,
        )
        self.assertIsNone(result)
        entry = fstab.read_text(encoding="utf-8")
        self.assertIn("UUID=home-uuid", entry)
        self.assertIn("/home", entry)
        self.assertIn("defaults,noatime", entry)

    def test_encrypted_home_uses_mapper(self):
        result, fstab = self.run_guard([{
            "mountPoint": "/home",
            "fs": "ext4",
            "uuid": "encrypted-uuid",
            "luksMapperName": "crypt-home",
        }])
        self.assertIsNone(result)
        self.assertIn("/dev/mapper/crypt-home", fstab.read_text(encoding="utf-8"))

    def test_unidentifiable_home_stops_install(self):
        result, _fstab = self.run_guard([{"mountPoint": "/home", "fs": "ext4"}])
        self.assertIsInstance(result, tuple)
        self.assertIn("no usable filesystem identifier", result[1])

    def test_duplicate_home_plan_stops_install(self):
        home = {"mountPoint": "/home", "fs": "ext4", "uuid": "one"}
        result, _fstab = self.run_guard([home, dict(home, uuid="two")])
        self.assertIsInstance(result, tuple)
        self.assertIn("more than one", result[1])

    def test_guard_is_loaded_immediately_after_fstab(self):
        settings = SETTINGS.read_text(encoding="utf-8")
        self.assertIn("modules-search: [ /etc/calamares/modules,", settings)
        self.assertIn("- fstab\n      - spacedfstabguard\n", settings)
        self.assertTrue((MODULE_DIR / "module.desc").is_file())


if __name__ == "__main__":
    unittest.main()
