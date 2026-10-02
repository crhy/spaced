"""Issues #237 and #250: refresh appstream before listing Flatpak updates."""
from pathlib import Path
import importlib.util
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True

try:
    _spec = importlib.util.spec_from_file_location(
        'spaced_update_appstream',
        ROOT / 'overlays/usr/lib/spaced-linux/spaced-update.py')
    spaced_update = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(spaced_update)
except Exception:
    spaced_update = None


@unittest.skipIf(spaced_update is None, 'needs PyGObject/GTK')
class AppstreamRefreshTests(unittest.TestCase):
    def fake_flatpak(self, refresh_fails=False):
        calls = []

        def run_capture(command, timeout=60):
            calls.append(command)
            if command[:2] == ['flatpak', 'list']:
                return 'io.github.crhy.rhYciv\tsystem\tapp/io.github.crhy.rhYciv/x86_64/master\trhYciv\n'
            if command[:2] == ['flatpak', 'remotes']:
                return 'spaced-github\tsystem\n'
            if command[:3] == ['flatpak', 'update', '--appstream']:
                if refresh_fails:
                    raise RuntimeError('offline')
                return ''
            if command[:2] == ['flatpak', 'remote-ls']:
                return 'app/io.github.crhy.rhYciv/x86_64/master\n'
            raise AssertionError(command)
        return calls, run_capture

    def run_enumerate(self, refresh_fails=False):
        calls, fake = self.fake_flatpak(refresh_fails)
        with mock.patch.object(spaced_update, 'run_capture', fake), \
                mock.patch.object(spaced_update, 'flatpak_available', return_value=True):
            warnings = []
            items = spaced_update.enumerate_flatpak(warnings=warnings)
        return calls, items, warnings

    def test_appstream_is_refreshed_before_updates_are_listed(self):
        calls, items, _warnings = self.run_enumerate()
        refresh = ['flatpak', 'update', '--appstream', '--noninteractive', '--system', 'spaced-github']
        self.assertIn(refresh, calls)
        listing = next(i for i, c in enumerate(calls) if c[:2] == ['flatpak', 'remote-ls'])
        self.assertLess(calls.index(refresh), listing)
        self.assertEqual(len(items), 1)

    def test_failed_refresh_still_lists_updates(self):
        _calls, items, warnings = self.run_enumerate(refresh_fails=True)
        self.assertEqual(len(items), 1)
        self.assertEqual(warnings, [])


if __name__ == '__main__':
    unittest.main()
