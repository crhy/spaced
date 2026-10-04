"""A global GTK3 override must not leak into GTK4 applications (#270)."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

HELPER = Path(__file__).resolve().parents[1] / 'overlays/usr/local/bin/spaced-flatpak-theme-migration'


class FlatpakThemeMigrationTests(unittest.TestCase):
    def test_migration_runs_once_and_retries_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fakebin = root / 'bin'
            fakebin.mkdir()
            flatpak = fakebin / 'flatpak'
            flatpak.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$HOME/calls"\nexit "${FAIL:-0}"\n')
            flatpak.chmod(0o755)
            env = dict(os.environ, HOME=str(root), XDG_CONFIG_HOME=str(root / 'config'),
                       XDG_DATA_HOME=str(root / 'data'), PATH=str(fakebin) + ':' + os.environ['PATH'])
            marker = root / 'config/spaced/flatpak-theme-10.26.1'
            old_marker = root / 'data/themes/.spaced-gtk-theme'
            old_marker.parent.mkdir(parents=True)
            old_marker.write_text('Spaced-Dark')
            failed = subprocess.run(['bash', str(HELPER)], env=dict(env, FAIL='1'))
            self.assertNotEqual(failed.returncode, 0)
            self.assertFalse(marker.exists())
            subprocess.run(['bash', str(HELPER)], env=env, check=True)
            self.assertTrue(marker.exists())
            self.assertFalse(old_marker.exists())
            subprocess.run(['bash', str(HELPER)], env=env, check=True)
            self.assertEqual((root / 'calls').read_text().splitlines(),
                             ['override --user --unset-env=GTK_THEME'] * 2)
