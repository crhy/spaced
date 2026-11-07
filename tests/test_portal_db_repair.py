"""A damaged Flatpak portal database must not break every file dialog (#408)."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
XSESSION = REPO / 'overlays/etc/X11/Xsession.d/26spaced-portal-db-repair'
GVDB = b'GVariant' + bytes(16)


class PortalDbRepairTests(unittest.TestCase):
    def run_xsession(self, home, **extra):
        env = {'PATH': os.environ['PATH'], 'HOME': str(home), **extra}
        # /etc/X11/Xsession sources these scripts under set -e.
        subprocess.run(['sh', '-ec', XSESSION.read_text(encoding='utf-8')], env=env, check=True)

    def test_damaged_tables_are_moved_aside_and_valid_ones_kept(self):
        for custom_data in (False, True):
            with self.subTest(custom_data=custom_data), tempfile.TemporaryDirectory() as temporary:
                home = Path(temporary)
                data = home / ('data' if custom_data else '.local/share')
                db = data / 'flatpak/db'
                db.mkdir(parents=True)
                (db / 'documents').write_bytes(b'')
                (db / 'devices').write_bytes(b'garbage!' + bytes(16))
                (db / 'notifications').write_bytes(GVDB)
                (db / 'background').write_bytes(b'raVGtnai' + bytes(16))
                (db / 'documents.ABC123').write_bytes(b'')
                extra = {'XDG_DATA_HOME': str(data)} if custom_data else {}
                self.run_xsession(home, **extra)
                names = sorted(path.name for path in db.iterdir())
                self.assertNotIn('documents', names)
                self.assertNotIn('devices', names)
                self.assertEqual((db / 'notifications').read_bytes(), GVDB)
                self.assertTrue((db / 'background').is_file())
                self.assertTrue((db / 'documents.ABC123').is_file())
                self.assertEqual(sum(name.startswith('documents.corrupt-') for name in names), 1)
                self.assertEqual(sum(name.startswith('devices.corrupt-') for name in names), 1)
                # A second login leaves the quarantined copies alone.
                self.run_xsession(home, **extra)
                self.assertEqual(sorted(path.name for path in db.iterdir()), names)

    def test_missing_database_directory_is_harmless(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.run_xsession(Path(temporary))


if __name__ == '__main__':
    unittest.main()
