"""Crypttab checks use temporary targets; never access real block devices."""
from pathlib import Path
import tempfile
import unittest

from test_calamares_home_reuse import load_guard, ROOT


class EncryptedRootTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'etc').mkdir()
        self.path = self.root / 'etc/crypttab'
        self.partition = dict(mountPoint='/', luksMapperName='cryptroot',
                              luksUuid='11111111-2222-3333-4444-555555555555')

    def run_guard(self):
        return load_guard(dict(rootMountPoint=str(self.root),
                               partitions=[self.partition])).run()

    def test_missing_root_mapping_gets_real_passphrase_fallback(self):
        self.path.write_text('# preserved')
        self.assertIsNone(self.run_guard())
        self.assertEqual(self.path.read_text(), '# preserved\ncryptroot UUID=' +
                         self.partition['luksUuid'] + ' none luks\n')
        first = self.path.read_bytes()
        self.assertIsNone(self.run_guard())
        self.assertEqual(first, self.path.read_bytes())

    def test_inner_uuid_and_partuuid_cannot_substitute_for_luks_uuid(self):
        self.partition.pop('luksUuid')
        self.partition.update(uuid='inner', partUuid='partition')
        self.assertIsInstance(self.run_guard(), tuple)
        self.assertFalse(self.path.exists())

    def test_conflicting_or_duplicate_existing_mapping_stops_install(self):
        for text in ('cryptroot UUID=wrong none luks\n',
                     ('cryptroot UUID=' + self.partition['luksUuid'] + ' none luks\n') * 2):
            self.path.write_text(text)
            self.assertIsInstance(self.run_guard(), tuple)
            self.assertEqual(self.path.read_text(), text)

    def test_missing_existing_keyfile_stops_install(self):
        self.path.write_text('cryptroot UUID=' + self.partition['luksUuid'] +
                             ' /crypto_keyfile.bin luks\n')
        self.assertIsInstance(self.run_guard(), tuple)
        key = self.root / 'crypto_keyfile.bin'
        key.write_bytes(b'test key')
        self.assertIsNone(self.run_guard())
        self.assertEqual(key.stat().st_mode & 0o777, 0o400)

    def test_unencrypted_install_untouched(self):
        self.partition.pop('luksMapperName')
        self.assertIsNone(self.run_guard())
        self.assertFalse(self.path.exists())

    def test_crypttab_symlink_rejected(self):
        target = self.root / 'untouched'
        target.write_text('original')
        self.path.symlink_to(target)
        self.assertIsInstance(self.run_guard(), tuple)
        self.assertEqual(target.read_text(), 'original')

    def test_initramfs_unlock_support_is_in_image(self):
        self.assertIn('  - cryptsetup-initramfs\n', (ROOT / 'config/packages.yaml').read_text())
