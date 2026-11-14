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
PRERM = (ROOT / 'packages/spaced-mate-default-settings/DEBIAN/prerm').read_text()
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
    '/usr/lib/spaced-linux/spaced-policy-rc.d', '/usr/sbin/policy-rc.d',
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
    def configure(self, temp, *, fail_sed_for=None, fail_cat=False, crash_is_file=False,
                  foreign_policy=None):
        root = temp / 'root'
        for directory in ('etc/lightdm', 'etc/default', 'usr/sbin', 'var'):
            (root / directory).mkdir(parents=True, exist_ok=True)
        (root / 'usr/lib/spaced-linux').mkdir(parents=True, exist_ok=True)
        (root / 'etc/lightdm/lightdm.conf').write_text(LIGHTDM_CONF)
        (root / 'etc/lightdm/lightdm-gtk-greeter.conf').write_text(GREETER_CONF)
        (root / 'etc/default/rcS').write_text(RCS)
        if foreign_policy is not None:
            (root / 'usr/sbin/policy-rc.d').write_text(foreign_policy)
        if crash_is_file:
            (root / 'var/crash').write_text('not a directory\n')
        bin_dir = temp / 'bin'
        bin_dir.mkdir(exist_ok=True)
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


class SessionGuardTests(unittest.TestCase):
    """The settings package must install the Spaced session guard.

    The distribution's elogind maintainer scripts stop and start the daemon on
    every upgrade through invoke-rc.d, which drops the running desktop session,
    empties /run/user/<uid> and leaves Flatpak applications without name
    resolution or sound until the PC is restarted. invoke-rc.d obeys
    /usr/sbin/policy-rc.d, so the settings postinst points it at the shipped
    guard, but never overwrites a policy the administrator already owns.
    """

    def guard_target(self, root):
        return str(root / 'usr/lib/spaced-linux/spaced-policy-rc.d')

    def test_the_guard_is_linked_in_when_no_policy_exists(self):
        with tempfile.TemporaryDirectory() as temp:
            result, root = FakeRootConfigureTests().configure(Path(temp))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn('session guard', result.stderr)
            policy = root / 'usr/sbin/policy-rc.d'
            self.assertTrue(policy.is_symlink(), f'{policy} was not installed')
            self.assertEqual(os.readlink(str(policy)), self.guard_target(root))

    def test_reconfiguring_keeps_one_guard_and_stays_quiet(self):
        with tempfile.TemporaryDirectory() as temp:
            first, root = FakeRootConfigureTests().configure(Path(temp))
            self.assertEqual(first.returncode, 0, first.stderr)
            second, _ = FakeRootConfigureTests().configure(Path(temp))
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertNotIn('session guard', second.stderr)
            self.assertEqual(os.readlink(str(root / 'usr/sbin/policy-rc.d')),
                             self.guard_target(root))

    def test_a_foreign_policy_is_left_alone_and_reported(self):
        foreign = '#!/bin/sh\nexit 0\n'
        with tempfile.TemporaryDirectory() as temp:
            result, root = FakeRootConfigureTests().configure(
                Path(temp), foreign_policy=foreign)
            self.assertEqual(result.returncode, 0, result.stderr)
            policy = root / 'usr/sbin/policy-rc.d'
            self.assertFalse(policy.is_symlink())
            self.assertEqual(policy.read_text(), foreign)
            self.assertIn('session guard was not installed', result.stderr)
            self.assertEqual(result.stderr.count('session guard was not installed'), 1)

    def test_a_missing_sbin_directory_cannot_leave_the_package_unconfigured(self):
        # The guard step is optional maintenance: nothing here may fail dpkg.
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'root'
            (root / 'etc/default').mkdir(parents=True)
            (root / 'etc/default/rcS').write_text(RCS)
            result = subprocess.run(['sh', '-c', in_fake_root(POSTINST, root), 'sh', 'configure'],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('ulimit -c 1048576', (root / 'etc/default/rcS').read_text())


class SessionGuardRemovalTests(unittest.TestCase):
    def remove(self, temp, prepare, argument='remove'):
        root = Path(temp) / 'root'
        (root / 'usr/sbin').mkdir(parents=True)
        (root / 'usr/lib/spaced-linux').mkdir(parents=True)
        guard = root / 'usr/lib/spaced-linux/spaced-policy-rc.d'
        guard.write_text('#!/bin/sh\nexit 0\n')
        policy = root / 'usr/sbin/policy-rc.d'
        prepare(policy, guard)
        result = subprocess.run(['sh', '-c', in_fake_root(PRERM, root), 'sh', argument],
                                capture_output=True, text=True)
        return result, policy

    def test_removal_deletes_only_the_symlink_this_package_made(self):
        with tempfile.TemporaryDirectory() as temp:
            result, policy = self.remove(Path(temp), lambda link, guard: link.symlink_to(guard))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(policy.exists() or policy.is_symlink())

    def test_removal_keeps_an_administrators_policy_script(self):
        with tempfile.TemporaryDirectory() as temp:
            result, policy = self.remove(
                Path(temp), lambda link, guard: link.write_text('#!/bin/sh\nexit 0\n'))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(policy.is_file())
            self.assertEqual(policy.read_text(), '#!/bin/sh\nexit 0\n')

    def test_removal_keeps_a_symlink_to_another_policy(self):
        with tempfile.TemporaryDirectory() as temp:
            result, policy = self.remove(
                Path(temp), lambda link, guard: link.symlink_to('/usr/local/sbin/my-policy'))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(policy.is_symlink())
            self.assertEqual(os.readlink(str(policy)), '/usr/local/sbin/my-policy')

    def test_an_upgrade_keeps_the_guard_installed(self):
        with tempfile.TemporaryDirectory() as temp:
            result, policy = self.remove(Path(temp), lambda link, guard: link.symlink_to(guard),
                                         'upgrade')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(policy.is_symlink())


if __name__ == '__main__':
    unittest.main()
