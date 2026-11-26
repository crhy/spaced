"""Executable inventory of rolling defaults that Spaced pins as policy."""
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "config/runtime-defaults.yaml"
PACKAGES = ROOT / "config/packages.yaml"


class RuntimeDefaultsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
        groups = yaml.safe_load(PACKAGES.read_text(encoding="utf-8"))
        cls.packages = {package for values in groups.values() for package in values}

    def test_manifest_schema_and_contract_ids(self):
        self.assertEqual(self.data.get("version"), 1)
        contracts = self.data.get("contracts")
        self.assertIsInstance(contracts, list)
        self.assertTrue(contracts)
        ids = [contract.get("id") for contract in contracts]
        self.assertEqual(len(ids), len(set(ids)), "runtime-default contract IDs repeat")
        self.assertTrue({"network-service-recovery", "lan-ipp-queues",
                         "grub-os-discovery", "desktop-smart-monitoring",
                         "signed-flatpak-remotes"}.issubset(ids))

    def test_every_contract_is_enforced_and_tested(self):
        for contract in self.data["contracts"]:
            with self.subTest(contract=contract.get("id")):
                for field in ("risk", "policy", "upstream"):
                    self.assertIsInstance(contract.get(field), str)
                    self.assertTrue(contract[field].strip())
                self.assertTrue(contract["upstream"].startswith("https://"))
                self.assertTrue(contract.get("enforcement"))
                self.assertTrue(contract.get("tests"))
                for test in contract["tests"]:
                    self.assertTrue((ROOT / test).is_file(), f"missing test: {test}")

    def test_packages_and_enforcement_tokens_are_real(self):
        for contract in self.data["contracts"]:
            with self.subTest(contract=contract["id"]):
                missing = set(contract.get("packages", ())) - self.packages
                self.assertEqual(missing, set(), f"packages absent from image: {missing}")
                for item in contract["enforcement"]:
                    path = ROOT / item["path"]
                    self.assertTrue(path.is_file(), f"missing enforcement file: {path}")
                    text = path.read_text(encoding="utf-8")
                    for token in item.get("contains", ()):
                        self.assertIn(token, text, f"{path} lost policy token {token!r}")


if __name__ == "__main__":
    unittest.main()
