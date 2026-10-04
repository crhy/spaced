"""The ISO cleanup must only discard package history and rebuildable indexes."""
from pathlib import Path
import subprocess
import tempfile
import unittest


HOOK = Path(__file__).resolve().parents[1] / 'scripts/iso/99-cleanup.chroot'


class ImageCleanupTests(unittest.TestCase):
    def test_preserves_documentation_hardware_and_other_caches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            keep = [
                'var/lib/dpkg/status', 'usr/share/doc/example/copyright',
                'usr/share/doc/example/NEWS.Debian.gz',
                'usr/share/doc/example/README', 'usr/share/man/man1/tool.1.gz',
                'usr/share/help/fr/tool/index.page', 'usr/share/locale/fr/tool.mo',
                'usr/lib/firmware/nvidia/test.bin', 'usr/lib/modules/test.ko',
                'var/cache/fontconfig/test.cache', 'var/cache/debconf/config.dat',
            ]
            discard = [
                'usr/share/doc/example/changelog.gz',
                'usr/share/doc/example/changelog.Debian.gz',
                'usr/share/doc/example/ChangeLog',
                'var/cache/apt/pkgcache.bin', 'var/cache/apt/srcpkgcache.bin',
            ]
            for name in keep + discard:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(name)
            # Directory symlinks must not make find traverse external data.
            external = root / 'outside'
            external.mkdir()
            (external / 'changelog').write_text('preserve')
            (root / 'usr/share/doc/external').symlink_to(external)
            (root / 'usr/share/doc/example/changelog-link').symlink_to('changelog.gz')
            for _ in range(2):  # Re-running the hook is harmless.
                subprocess.run(['bash', str(HOOK), str(root)], check=True)
                for name in keep:
                    self.assertEqual((root / name).read_text(), name)
                for name in discard:
                    self.assertFalse((root / name).exists())
                self.assertFalse((root / 'usr/share/doc/example/changelog-link').is_symlink())
                self.assertEqual((external / 'changelog').read_text(), 'preserve')

    def test_rejects_unpopulated_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(['bash', str(HOOK), tmp], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
