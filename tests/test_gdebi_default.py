"""GDebi is preinstalled and opens .deb files by default."""
import configparser
import yaml
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MIMEAPPS = ROOT / "overlays/usr/share/applications/mimeapps.list"
PACKAGES = ROOT / "config/packages.yaml"
DEB_TYPE = "application/vnd.debian.binary-package"


class GDebiDefaultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parser = configparser.ConfigParser(interpolation=None, strict=False)
        parser.optionxform = str
        parser.read_string(MIMEAPPS.read_text(encoding="utf-8"))
        cls.mimeapps = parser
        groups = yaml.safe_load(PACKAGES.read_text(encoding="utf-8"))
        cls.packages = [package for group in groups.values() for package in group]

    def test_default_application_section_maps_deb_to_gdebi(self):
        value = self.mimeapps["Default Applications"][DEB_TYPE]
        self.assertEqual(value.rstrip(";"), "gdebi.desktop")

    def test_added_associations_section_maps_deb_to_gdebi(self):
        value = self.mimeapps["Added Associations"][DEB_TYPE]
        self.assertEqual(value.rstrip(";"), "gdebi.desktop")

    def test_gdebi_is_listed_exactly_once(self):
        self.assertEqual(self.packages.count("gdebi"), 1)

    def test_gdebi_core_is_listed_exactly_once(self):
        self.assertEqual(self.packages.count("gdebi-core"), 1)


if __name__ == "__main__":
    unittest.main()
