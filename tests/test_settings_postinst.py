"""Issue #415: a failed optional step must not leave a Spaced package half-configured.

Runs the whole spaced-mate-default-settings postinst against a scratch root and
stub commands, so nothing on this computer is changed.
"""
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
POSTINST = (ROOT / 'packages/spaced-mate-default-settings/DEBIAN/postinst').read_text()
REAL_SED = shutil.which('sed')
OLD_IMAGE = '/usr/share/icons/hicolor/256x256/apps/spaced-linux.png'
NEW_IMAGE = '/usr/share/pixmaps/spaced-medallion.png'
LIGHTDM_CONF = '[Seat:*]\nautologin-user=user\nautologin-user-timeout=0\nallow-guest=false\n'
GREETER_CONF = f'[greeter]\ndefault-user-image={OLD_IMAGE}\nbackground=#292C2F\n'
RCS = 'PATH=/sbin:/bin\n'

# Every absolute path the postinst reads, tests or writes. The sed patterns keep
# their host paths, so the migrations themselves are exercised unchanged.
FAKE_PATHS = (
    '/etc/lightdm/lightdm.conf', '/etc/lightdm/lightdm-gtk-greeter.conf',
    '/etc/default/rcS', '/etc/sysctl.d/60-spaced-coredump.conf',
    '/etc/init.d/spaced-first-boot-snapshot', '/etc/init.d/spaced-wsdd',
    '/usr/lib/spaced-linux/spaced-clean-duplicate-apt-source',
    '/usr/share/glib-2.0/schemas', '/usr/share/applications',
    '/usr/local/share/applications', '/usr/share/flatpak', '/usr/bin/flatpak',
    '/var/crash',
)


def in_fake_root(script, root):
    """Rewrite the postinst's absolute paths into a scratch root in one pass."""
    pattern = re.compile(
        '|'.join(re.escape(path) for path in sorted(FAKE_PATHS, key=len, reverse=True)))
    return pattern.sub(lambda match: f'{root}{match.group(0)}', script)


class FakeRootConfigureTests(unittest.TestCase):
    def configure(self, temp, *, fail_sed_for=None, fail_cat=False, crash_is_file=False):
        root = temp / 'root'
        for directory in ('etc/lightdm', 'etc/default', 'var'):
            (root / directory).mkdir(parents=True)
        (root / 'etc/lightdm/lightdm.conf').write_text(LIGHTDM_CONF)
        (root / 'etc/lightdm/lightdm-gtk-greeter.conf').write_text(GREETER_CONF)
        (root / 'etc/default/rcS').write_text(RCS)
        if crash_is_file:
            (root / 'var/crash').write_text('not a directory\n')
        bin_dir = temp / 'bin'
        bin_dir.mkdir()
        if fail_sed_for:
            self.write_stub(bin_dir, 'sed', (
                'for arg in "$@"; do\n'
                f'    case "$arg" in *{fail_sed_for}) '
                'echo "sed: cannot rename $arg: Read-only file system" >&2; exit 4;;\n'
                '    esac\n'
                'done\n'
                f'exec "{REAL_SED}" "$@"'))
        if fail_cat:
            self.write_stub(bin_dir, 'cat',
                            'echo "cat: cannot write: Read-only file system" >&2; exit 1')
        env = dict(os.environ, PATH=f'{bin_dir}{os.pathsep}{os.environ["PATH"]}',
                   TMPDIR=str(temp))
        result = subprocess.run(['sh', '-c', in_fake_root(POSTINST, root), 'sh', 'configure'],
                                env=env, capture_output=True, text=True)
        return result, root

    @staticmethod
    def write_stub(bin_dir, name, body):
        stub = bin_dir / name
        stub.write_text(f'#!/bin/sh\n{body}\n')
        stub.chmod(0o755)

    def assert_reached_the_end(self, result, root):
        """The steps after the injected failure must still have run."""
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('ulimit -c 1048576', (root / 'etc/default/rcS').read_text())

    def test_every_migration_runs_against_the_scratch_root(self):
        with tempfile.TemporaryDirectory() as temp:
            result, root = self.configure(Path(temp))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn('autologin-user', (root / 'etc/lightdm/lightdm.conf').read_text())
            self.assertIn(f'default-user-image={NEW_IMAGE}',
                          (root / 'etc/lightdm/lightdm-gtk-greeter.conf').read_text())
            self.assertEqual(stat.S_IMODE(os.stat(root / 'var/crash').st_mode), 0o1777)
            self.assertIn('ulimit -c 1048576', (root / 'etc/default/rcS').read_text())

    def test_lightdm_autologin_migration_failure_still_configures_the_package(self):
        # a08-02: an unwritable package-owned LightDM base file must not leave
        # the settings package (and spaced-meta, which depends on it) broken.
        with tempfile.TemporaryDirectory() as temp:
            result, root = self.configure(Path(temp), fail_sed_for='lightdm.conf')
            self.assert_reached_the_end(result, root)
            self.assertIn('autologin-user=user', (root / 'etc/lightdm/lightdm.conf').read_text())
            self.assertIn(f'default-user-image={NEW_IMAGE}',
                          (root / 'etc/lightdm/lightdm-gtk-greeter.conf').read_text())
            self.assertTrue((root / 'var/crash').is_dir())

    def test_greeter_avatar_migration_failure_still_configures_the_package(self):
        with tempfile.TemporaryDirectory() as temp:
            result, root = self.configure(Path(temp), fail_sed_for='lightdm-gtk-greeter.conf')
            self.assert_reached_the_end(result, root)
            self.assertNotIn('autologin-user', (root / 'etc/lightdm/lightdm.conf').read_text())
            self.assertIn(f'default-user-image={OLD_IMAGE}',
                          (root / 'etc/lightdm/lightdm-gtk-greeter.conf').read_text())
            self.assertTrue((root / 'var/crash').is_dir())

    def test_crash_directory_failure_still_configures_the_package(self):
        with tempfile.TemporaryDirectory() as temp:
            result, root = self.configure(Path(temp), crash_is_file=True)
            self.assert_reached_the_end(result, root)
            self.assertFalse((root / 'var/crash').is_dir())

    def test_core_limit_append_failure_still_configures_the_package(self):
        with tempfile.TemporaryDirectory() as temp:
            result, root = self.configure(Path(temp), fail_cat=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('Read-only file system', result.stderr)
            self.assertEqual((root / 'etc/default/rcS').read_text(), RCS)
            self.assertEqual(stat.S_IMODE(os.stat(root / 'var/crash').st_mode), 0o1777)


if __name__ == '__main__':
    unittest.main()
