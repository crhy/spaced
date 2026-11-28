"""crhy/spacedupdate#16: offer an update whose newer version sits in a remote
the app was not installed from. Flatpak's own update query matches an installed
ref only against its recorded origin remote, so an app installed from a per-app
remote is invisible to the shared remote that carries the newer build. The fix
compares each installation's installed versions against every enabled remote.

No network and no real flatpak: run_capture is mocked with this machine's exact
answers (SpacedBazaar installed twice - user 0.1.14, system 0.1.15 - origin
remote absent from the user scope, shared spaced-github carrying 0.1.15).
"""
from pathlib import Path
import importlib.util
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True

try:
    _spec = importlib.util.spec_from_file_location(
        'spaced_update_fp_versions',
        ROOT / 'overlays/usr/lib/spaced-linux/spaced-update.py')
    spaced_update = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(spaced_update)
except Exception:
    spaced_update = None


DISPLAY = (
    'io.github.crhy.SpacedBazaar\tuser\tapp/io.github.crhy.SpacedBazaar/x86_64/master\tSpacedBazaar\n'
    'io.github.crhy.SpacedBazaar\tsystem\tapp/io.github.crhy.SpacedBazaar/x86_64/master\tSpacedBazaar\n'
)


def scope_of(command):
    if '--user' in command:
        return 'user'
    if '--system' in command:
        return 'system'
    return None


@unittest.skipIf(spaced_update is None, 'needs PyGObject/GTK')
class FlatpakUpdateVersionsTests(unittest.TestCase):
    def fake(self, remote_versions_map, remotes_map, raise_remote=None):
        list_calls = []
        version_calls = []

        def run_capture(command, timeout=60):
            if command[:2] == ['flatpak', 'list'] and '--columns=application,installation,ref,name' in command:
                return DISPLAY
            if command[:2] == ['flatpak', 'list'] and '--columns=application,branch,version' in command:
                list_calls.append(command)
                scope = scope_of(command)
                version = remote_versions_map[scope]
                return f'io.github.crhy.SpacedBazaar\tmaster\t{version}\n'
            if command[:2] == ['flatpak', 'remotes']:
                return '\n'.join(
                    f'{name}\t{opts}' for name, opts in remotes_map[scope_of(command)])
            if command[:3] == ['flatpak', 'update', '--appstream']:
                return ''
            if command[:2] == ['flatpak', 'remote-ls']:
                remote = command[2]
                scope = scope_of(command)
                version_calls.append((scope, remote))
                if raise_remote and (scope, remote) == raise_remote:
                    raise RuntimeError('offline')
                version = remote_versions_map.get((scope, remote), remote_versions_map[scope])
                return f'io.github.crhy.SpacedBazaar\tmaster\t{version}\n'
            raise AssertionError(command)
        return run_capture, list_calls, version_calls

    def enumerate_with(self, remote_versions_map, remotes_map, raise_remote=None, warnings=None, stats=None):
        run_capture, list_calls, version_calls = self.fake(
            remote_versions_map, remotes_map, raise_remote)
        with mock.patch.object(spaced_update, 'run_capture', run_capture), \
                mock.patch.object(spaced_update, 'flatpak_available', return_value=True):
            items = spaced_update.enumerate_flatpak(warnings=warnings, stats=stats)
        return items, list_calls, version_calls

    def test_newer_version_in_a_non_origin_remote_is_offered(self):
        # user installed 0.1.14, shared spaced-github carries 0.1.15 (not the
        # user install's origin): the update is offered; the system install at
        # 0.1.15 is not.
        remote_versions_map = {
            'user': '0.1.14', 'system': '0.1.15',
            ('user', 'spaced-github'): '0.1.15', ('system', 'spaced-github'): '0.1.15',
        }
        remotes_map = {'user': [('spaced-github', 'enabled')],
                       'system': [('spaced-github', 'enabled')]}
        stats = {'remotes_total': 0, 'remotes_failed': 0}
        items, list_calls, version_calls = self.enumerate_with(
            remote_versions_map, remotes_map, stats=stats)
        self.assertEqual([(i['scope'], i['name']) for i in items], [('user', 'io.github.crhy.SpacedBazaar')])
        # Flatpak's --updates query is gone: one installed-version listing per
        # installation and a version listing per (scope, remote).
        self.assertEqual(len(list_calls), 2)
        self.assertEqual(sorted(version_calls),
                         [('system', 'spaced-github'), ('user', 'spaced-github')])
        self.assertEqual(stats['remotes_total'], 2)

    def test_equal_version_is_not_offered(self):
        remote_versions_map = {
            'user': '0.1.15', 'system': '0.1.15',
            ('user', 'spaced-github'): '0.1.15', ('system', 'spaced-github'): '0.1.15',
        }
        remotes_map = {'user': [('spaced-github', 'enabled')],
                       'system': [('spaced-github', 'enabled')]}
        items, _l, _v = self.enumerate_with(remote_versions_map, remotes_map, warnings=[])
        self.assertEqual(items, [])

    def test_older_remote_version_is_not_offered(self):
        remote_versions_map = {
            'user': '0.2.0', 'system': '0.2.0',
            ('user', 'spaced-github'): '0.1.0', ('system', 'spaced-github'): '0.1.0',
        }
        remotes_map = {'user': [('spaced-github', 'enabled')],
                       'system': [('spaced-github', 'enabled')]}
        items, _l, _v = self.enumerate_with(remote_versions_map, remotes_map, warnings=[])
        self.assertEqual(items, [])

    def test_disabled_remote_is_never_consulted(self):
        remote_versions_map = {
            'user': '0.1.14', 'system': '0.1.15',
            ('user', 'spaced-github'): '0.1.15', ('system', 'spaced-github'): '0.1.15',
        }
        remotes_map = {'user': [('spaced-github', 'enabled'), ('dead-origin', 'disabled')],
                       'system': [('spaced-github', 'enabled')]}
        _items, _l, version_calls = self.enumerate_with(
            remote_versions_map, remotes_map, warnings=[])
        self.assertNotIn(('user', 'dead-origin'), version_calls)

    def test_failing_remote_warns_but_still_offers_healthy_update(self):
        remote_versions_map = {
            'user': '0.1.14', 'system': '0.1.15',
            ('user', 'flathub'): '0.1.15',
        }
        remotes_map = {'user': [('flathub', 'enabled'), ('brutal-local', 'enabled')],
                       'system': [('spaced-github', 'enabled')]}
        warnings = []
        stats = {'remotes_total': 0, 'remotes_failed': 0}
        items, _l, _v = self.enumerate_with(
            remote_versions_map, remotes_map,
            raise_remote=('user', 'brutal-local'), warnings=warnings, stats=stats)
        self.assertEqual([(i['scope'], i['name']) for i in items],
                         [('user', 'io.github.crhy.SpacedBazaar')])
        self.assertTrue(any('brutal-local' in w for w in warnings))
        self.assertEqual(stats['remotes_failed'], 1)
        self.assertEqual(stats['remotes_total'], 3)

    def test_raising_remote_without_warning_list_still_raises(self):
        remote_versions_map = {
            'user': '0.1.14', 'system': '0.1.15',
            ('user', 'flathub'): '0.1.15',
        }
        remotes_map = {'user': [('brutal-local', 'enabled')],
                       'system': [('spaced-github', 'enabled')]}
        with self.assertRaises(RuntimeError):
            self.enumerate_with(remote_versions_map, remotes_map,
                                raise_remote=('user', 'brutal-local'), warnings=None)

    def test_remote_versions_parses_and_uses_timeout(self):
        seen = {}

        def run_capture(command, timeout=60):
            seen['command'] = command
            seen['timeout'] = timeout
            return 'io.github.crhy.rhYciv\tstable\t0.2.3\n'

        with mock.patch.object(spaced_update, 'run_capture', run_capture):
            versions = spaced_update.remote_versions('user', 'spaced-github')
        self.assertEqual(versions, {('io.github.crhy.rhYciv', 'stable'): '0.2.3'})
        self.assertEqual(seen['timeout'], 90)

    def test_installed_versions_one_listing_per_installation(self):
        calls = []

        def run_capture(command, timeout=60):
            calls.append(command)
            return 'io.github.crhy.rhYciv\tmaster\t0.2.3\n'

        with mock.patch.object(spaced_update, 'run_capture', run_capture):
            versions = spaced_update.installed_versions('user')
        self.assertEqual(len(calls), 1)
        self.assertIn('--user', calls[0])
        self.assertEqual(versions, {('io.github.crhy.rhYciv', 'master'): '0.2.3'})

    def test_version_key_orders_calendar_not_lexically(self):
        key = spaced_update.version_key
        self.assertTrue(key('0.1.14') < key('0.1.15'))
        self.assertTrue(key('9.26') < key('10.26'))
        self.assertTrue(key('10.26') < key('1.27'))

    def test_ref_branch_reads_last_component(self):
        ref_branch = spaced_update.ref_branch
        self.assertEqual(ref_branch('app/io.github.crhy.rhYciv/x86_64/master'), 'master')
        self.assertEqual(ref_branch('runtime/org.gimp.GIMP/x86_64/2.10'), '2.10')
        self.assertEqual(ref_branch('io.github.crhy.rhYciv/x86_64/master'), 'master')
        self.assertEqual(ref_branch('app/io.github.crhy.rhYciv'), '')


if __name__ == '__main__':
    unittest.main()
