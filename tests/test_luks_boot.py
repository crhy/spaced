"""Issue #420: an encrypted install must boot, not drop to (initramfs).

The image is built with APT recommends switched off, so the package that
provides the initramfs cryptroot hook has to be named explicitly, and the
installed system must keep it.  These tests read the real generated package
list, the real Calamares sequence and the real guard module rather than
repeating the expectations here.
"""
from pathlib import Path
import importlib.util
import re
import subprocess
import sys
import tempfile
import types
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True

PACKAGES_YAML = ROOT / "config" / "packages.yaml"
PACKAGE_LIST = ROOT / "scripts" / "iso" / "package-list.sh"
LOCAL_PACKAGES = ROOT / "scripts" / "iso" / "build-local-packages.sh"
LB_CONFIG = ROOT / "live-build" / "auto" / "config"
SETTINGS = ROOT / "overlays" / "etc" / "calamares" / "settings.conf"
PACKAGES_CONF = ROOT / "overlays" / "etc" / "calamares" / "modules" / "packages.conf"
GUARD_DIR = ROOT / "overlays" / "etc" / "calamares" / "modules" / "spacedfstabguard"

HOOK_PACKAGE = "cryptsetup-initramfs"
KEYFILE = "/crypto_keyfile.bin"


def generated_packages():
    result = subprocess.run(
        ["bash", str(PACKAGE_LIST)], capture_output=True, text=True, check=True
    )
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def package_groups():
    return yaml.safe_load(PACKAGES_YAML.read_text(encoding="utf-8"))


def meta_excluded_groups():
    """The groups build-local-packages.sh keeps out of spaced-meta Depends."""
    match = re.search(r"if group not in \{([^}]*)\}", LOCAL_PACKAGES.read_text(encoding="utf-8"))
    if not match:
        raise AssertionError("build-local-packages.sh has no 'if group not in {...}' group filter")
    return {name.strip().strip("'\"") for name in match.group(1).split(",")}


def meta_runtime_packages():
    return {
        package
        for group, packages in package_groups().items()
        if group not in meta_excluded_groups()
        for package in packages
    }


def installer_removed_packages():
    """The packages Calamares' apt backend removes from the installed system."""
    config = yaml.safe_load(PACKAGES_CONF.read_text(encoding="utf-8"))
    removed = set()
    for operation in config["operations"]:
        removed.update(operation.get("remove", ()))
    return removed


def exec_modules():
    settings = yaml.safe_load(SETTINGS.read_text(encoding="utf-8"))
    return next(phase["exec"] for phase in settings["sequence"] if "exec" in phase)


def load_guard(values):
    fake = types.SimpleNamespace(
        globalstorage=types.SimpleNamespace(value=values.get),
        utils=types.SimpleNamespace(
            warning=lambda _message: None, debug=lambda _message: None
        ),
    )
    old = sys.modules.get("libcalamares")
    sys.modules["libcalamares"] = fake
    try:
        spec = importlib.util.spec_from_file_location(
            "spacedfstabguard", GUARD_DIR / "main.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if old is None:
            del sys.modules["libcalamares"]
        else:
            sys.modules["libcalamares"] = old


class EncryptedBootPackageTests(unittest.TestCase):
    def test_cryptsetup_and_its_initramfs_hook_are_in_the_image(self):
        packages = generated_packages()
        self.assertIn("cryptsetup", packages)
        self.assertIn(HOOK_PACKAGE, packages)

    def test_the_hook_package_reaches_installed_systems_and_updates(self):
        self.assertIn(HOOK_PACKAGE, meta_runtime_packages())
        self.assertIn("cryptsetup", meta_runtime_packages())

    def test_the_installer_keeps_the_encryption_tools(self):
        removed = installer_removed_packages()
        self.assertEqual(
            sorted({HOOK_PACKAGE, "cryptsetup"}.intersection(removed)), [],
            "the installed system loses the package that unlocks LUKS at boot",
        )

    def test_recommends_are_off_so_the_hook_must_be_named(self):
        self.assertIn("--apt-recommends false", LB_CONFIG.read_text(encoding="utf-8"))
        self.assertIn(
            HOOK_PACKAGE,
            PACKAGES_YAML.read_text(encoding="utf-8"),
            "cryptsetup's Recommends is never resolved during the image build",
        )

    def test_the_unlock_path_stays_sysvinit(self):
        text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (SETTINGS, PACKAGES_YAML, PACKAGES_CONF)
        )
        for systemd_name in ("systemd-cryptsetup", "cryptsetup-systemd", "cryptsetup.service"):
            self.assertNotIn(systemd_name, text)


class CalamaresLuksSequenceTests(unittest.TestCase):
    def test_the_luks_boot_sequence_is_kept_in_order(self):
        modules = exec_modules()
        for step in ("luksbootkeyfile", "fstab", "spacedfstabguard", "initramfscfg", "initramfs"):
            self.assertIn(step, modules, f"Calamares no longer runs {step}")
        self.assertLess(modules.index("luksbootkeyfile"), modules.index("fstab"))
        self.assertLess(modules.index("fstab"), modules.index("spacedfstabguard"))
        self.assertLess(
            modules.index("spacedfstabguard"),
            modules.index("initramfs"),
            "the crypttab guard must run before the installed initramfs is built",
        )
        self.assertLess(modules.index("initramfscfg"), modules.index("initramfs"))

    def test_the_target_initramfs_is_refreshed_after_the_package_install(self):
        modules = exec_modules()
        self.assertLess(modules.index("packages"), modules.index("initramfs"))
        postinstall = (
            ROOT / "overlays" / "etc" / "calamares" / "modules"
            / "shellprocess@spaced-postinstall.conf"
        ).read_text(encoding="utf-8")
        self.assertIn("update-initramfs -u -k all", postinstall)


class CrypttabGuardTests(unittest.TestCase):
    def encrypted_root(self, **overrides):
        partition = {
            "mountPoint": "/",
            "fs": "ext4",
            "device": "/dev/nvme0n1p2",
            "luksMapperName": "luks-8a7016fb",
            "luksUuid": "8a7016fb",
            "uuid": "1c39aa5c",
        }
        partition.update(overrides)
        return partition

    def run_guard(self, partitions, initial_crypttab=None, target_files=()):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / "etc").mkdir()
        if initial_crypttab is not None:
            (root / "etc" / "crypttab").write_text(initial_crypttab, encoding="utf-8")
        for name in target_files:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("key", encoding="utf-8")
        guard = load_guard({"partitions": partitions, "rootMountPoint": str(root)})
        return guard.run(), root

    def crypttab(self, root):
        path = root / "etc" / "crypttab"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def test_missing_crypttab_entry_is_written_with_the_keyfile(self):
        result, root = self.run_guard([self.encrypted_root()], target_files=["crypto_keyfile.bin"])
        self.assertIsNone(result)
        entry = self.crypttab(root)
        self.assertIn("luks-8a7016fb", entry)
        self.assertIn("UUID=8a7016fb", entry)
        self.assertIn(KEYFILE, entry)

    def test_the_luks_container_is_named_not_the_filesystem_inside_it(self):
        _result, root = self.run_guard([self.encrypted_root()])
        self.assertNotIn("UUID=1c39aa5c", self.crypttab(root))

    def test_an_existing_entry_is_left_alone(self):
        original = "luks-8a7016fb UUID=8a7016fb /crypto_keyfile.bin luks\n"
        _result, root = self.run_guard([self.encrypted_root()], initial_crypttab=original)
        self.assertEqual(self.crypttab(root), original)

    def test_an_unidentifiable_luks_volume_stops_the_install(self):
        partition = self.encrypted_root()
        for key in ("luksUuid", "partUuid", "uuid", "device"):
            partition.pop(key, None)
        result, root = self.run_guard([partition])
        self.assertIsInstance(result, tuple)
        self.assertIn("no usable LUKS identifier", result[1])
        self.assertEqual(self.crypttab(root), "")

    def test_the_boot_keyfile_is_copied_into_the_target(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name) / "root"
        (root / "etc").mkdir(parents=True)
        installer_keyfile = Path(temp.name) / "crypto_keyfile.bin"
        installer_keyfile.write_text("key", encoding="utf-8")
        guard = load_guard({"partitions": [], "rootMountPoint": str(root)})
        self.assertTrue(guard._ensure_boot_keyfile(str(root), source=str(installer_keyfile)))
        target = root / KEYFILE.lstrip("/")
        self.assertEqual(target.read_text(encoding="utf-8"), "key")
        self.assertEqual(target.stat().st_mode & 0o777, 0o400)

    def test_an_unencrypted_plan_needs_no_crypttab(self):
        result, root = self.run_guard([{"mountPoint": "/", "fs": "ext4", "uuid": "1c39aa5c"}])
        self.assertIsNone(result)
        self.assertEqual(self.crypttab(root), "")


if __name__ == "__main__":
    unittest.main()
