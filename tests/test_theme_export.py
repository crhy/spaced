"""Exercise the actual switcher's export block in an isolated filesystem."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SWITCHER = ROOT / 'overlays/usr/local/bin/spaced-switch-theme'


@unittest.skipUnless(shutil.which('rsync'), 'requires rsync')
class ThemeExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source/Spaced-Test/gtk-3.0/gtk.css'
        self.source.parent.mkdir(parents=True)
        self.source.write_text('old css')
        self.dest = self.root / 'data/themes/Spaced-Test/gtk-3.0/gtk.css'
        self.stamp = self.root / 'data/themes/.spaced-export-stamp'
        text = SWITCHER.read_text()
        block = text.split('if command -v flatpak >/dev/null 2>&1; then\n', 1)[1]
        self.block = block.split('    # GTK3 follows XSettings;', 1)[0]
        self.block = self.block.replace('/usr/share/themes', str(self.root / 'source'))
        self.env = dict(os.environ, HOME=str(self.root), XDG_DATA_HOME=str(self.root / 'data'))

    def export(self, prelude='flatpak() { return 0; }'):
        subprocess.run(['bash', '-euc', prelude + '\n' + self.block],
                       env=self.env, check=True, timeout=20)

    def test_nested_css_replacement_with_same_size_and_mtime_is_exported(self):
        self.export()
        old_stamp = self.stamp.read_text()
        source_stat = self.source.stat()
        parent_stat = self.source.parents[1].stat()
        self.source.write_text('new css')
        os.utime(self.source, ns=(source_stat.st_atime_ns, source_stat.st_mtime_ns))
        self.assertEqual(self.source.parents[1].stat().st_mtime_ns, parent_stat.st_mtime_ns)
        self.export()
        self.assertEqual(self.dest.read_text(), 'new css')
        self.assertNotEqual(self.stamp.read_text(), old_stamp)

    def test_unchanged_export_does_not_copy_again(self):
        self.export()
        self.export('flatpak() { return 0; }; rsync() { exit 51; }')

    def test_failed_copy_is_retried(self):
        self.export('flatpak() { return 0; }; rsync() { return 1; }')
        self.assertFalse(self.stamp.exists())
        self.export()
        self.assertEqual(self.dest.read_text(), 'old css')

    def test_failed_flatpak_permission_is_retried(self):
        self.export('flatpak() { return 1; }')
        self.assertFalse(self.stamp.exists())
        self.export()
        self.assertTrue(self.stamp.exists())


if __name__ == '__main__':
    unittest.main()
