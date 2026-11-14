"""A package update must never stop the elogind that owns a running desktop.

The distribution's elogind maintainer scripts call `invoke-rc.d elogind stop`
and `start` on every upgrade, which drops the live session, empties
/run/user/<uid> and leaves Flatpak applications without name resolution or
sound until the PC is restarted. `invoke-rc.d` asks /usr/sbin/policy-rc.d first,
and status 101 means "forbidden".

These cases run the shipped guard with a fake `pgrep` on PATH and a throwaway
SPACED_POLICY_RUN_USER directory, so this computer's real /run/user, X session
and /usr/sbin are never touched. No network, root, display or hardware needed.
"""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'overlays/usr/lib/spaced-linux/spaced-policy-rc.d'
GUARD_TARGET = '/usr/lib/spaced-linux/spaced-policy-rc.d'
INVOKE_RC_D = Path('/usr/sbin/invoke-rc.d')


class PolicyRcDTests(unittest.TestCase):
    def setUp(self):
        self.workspace = Path(tempfile.mkdtemp(prefix='spaced-policy-rc-d-'))
        self.addCleanup(shutil.rmtree, self.workspace, ignore_errors=True)
        self.run_user = self.workspace / 'run-user'
        self.run_user.mkdir()

    def use_desktop(self, *, xorg, runtime_session):
        """Fake the two ways a running desktop is recognised."""
        bin_dir = self.workspace / 'bin'
        bin_dir.mkdir(exist_ok=True)
        stub = bin_dir / 'pgrep'
        stub.write_text(f'#!/bin/sh\nexit {0 if xorg else 1}\n', encoding='utf-8')
        stub.chmod(0o755)
        if runtime_session:
            (self.run_user / '1000').mkdir(exist_ok=True)
        return bin_dir

    def run_guard(self, *arguments, xorg=False, runtime_session=False):
        bin_dir = self.use_desktop(xorg=xorg, runtime_session=runtime_session)
        env = dict(os.environ, PATH=f'{bin_dir}{os.pathsep}{os.environ["PATH"]}',
                   SPACED_POLICY_RUN_USER=str(self.run_user))
        return subprocess.run(['/bin/sh', str(SCRIPT), *arguments], env=env,
                              capture_output=True, text=True, timeout=30)

    def assert_status(self, status, *arguments, **desktop):
        result = self.run_guard(*arguments, **desktop)
        self.assertEqual(result.stdout, '', f'{arguments} wrote to stdout')
        self.assertEqual(result.returncode, status,
                         f'{arguments} -> {result.returncode}: {result.stderr}')
        return result

    def test_stopping_elogind_under_a_running_x_server_is_forbidden(self):
        self.assert_status(101, 'elogind', 'stop', xorg=True)

    def test_restarting_elogind_under_a_running_x_server_is_forbidden(self):
        self.assert_status(101, 'elogind', 'restart', xorg=True)

    def test_every_session_losing_action_is_forbidden(self):
        for action in ('stop', 'restart', 'try-restart', 'force-reload', 'reload'):
            self.assert_status(101, 'elogind', action, xorg=True)

    def test_a_running_login_session_without_xorg_is_enough(self):
        # /run/user/<uid> exists for the live desktop user even when the guard
        # cannot see the X server process.
        self.assert_status(101, 'elogind', 'stop', xorg=False, runtime_session=True)

    def test_leading_invoke_rc_d_options_and_one_action_list_argument(self):
        self.assert_status(101, '--quiet', 'elogind', 'stop start', xorg=True)
        self.assert_status(101, '--list', 'elogind', 'restart', '2', xorg=True)

    def test_starting_elogind_is_always_allowed(self):
        self.assert_status(0, 'elogind', 'start', xorg=True, runtime_session=True)
        self.assert_status(0, 'elogind', 'start', '2', xorg=True)

    def test_stopping_elogind_without_a_desktop_is_allowed(self):
        # A package upgrade in a chroot, a container or on a headless server
        # must still get its daemon restarted.
        self.assert_status(0, 'elogind', 'stop', xorg=False, runtime_session=False)
        self.assert_status(0, 'elogind', 'restart', xorg=False, runtime_session=False)

    def test_other_services_are_never_blocked(self):
        self.assert_status(0, 'cups', 'restart', xorg=True, runtime_session=True)
        self.assert_status(0, 'spaced-wsdd', 'stop', xorg=True, runtime_session=True)

    def test_elogind_status_and_querying_are_never_blocked(self):
        self.assert_status(0, 'elogind', 'status', xorg=True, runtime_session=True)
        self.assert_status(0, '--quiet', '--list', 'elogind', 'status', '2', xorg=True)

    def test_no_arguments_are_harmless(self):
        self.assert_status(0, xorg=True, runtime_session=True)

    def test_the_script_is_a_posix_sh_program_below_forty_lines(self):
        text = SCRIPT.read_text(encoding='utf-8')
        self.assertEqual(text.splitlines()[0], '#!/bin/sh')
        self.assertLess(len(text.splitlines()), 40)
        self.assertTrue(os.access(SCRIPT, os.X_OK))
        subprocess.run(['sh', '-n', str(SCRIPT)], check=True, timeout=30)

    @unittest.skipUnless(INVOKE_RC_D.is_file(), 'this host has no /usr/sbin/invoke-rc.d')
    def test_invoke_rc_d_itself_treats_status_101_as_forbidden(self):
        # Read the system's own invoke-rc.d instead of copying anything into a
        # system path: it maps the helper's 101 to "denied execution" and then
        # returns 0 to the maintainer script, which is what keeps the upgrade
        # transaction green while the daemon stays up.
        text = INVOKE_RC_D.read_text(encoding='utf-8', errors='replace')
        self.assertIn('/usr/sbin/policy-rc.d', text)
        self.assertIn('policy-rc.d denied execution', text)
        # querypolicy() turns the helper's 101 into a denial (only --force
        # overrides it), and the denied path ends in "exit 0" for the caller.
        denial = re.search(r'(?ms)^\s*101\).*?denied execution', text)
        self.assertIsNotNone(denial, 'invoke-rc.d has no 101 -> denied execution rule')
        returns_zero = re.search(r'(?ms)RC\} -eq 101.*?\n\s*RC=0', text)
        self.assertIsNotNone(returns_zero,
                             'a policy denial is not reported to the maintainer script as success')

    def test_the_settings_package_installs_the_guard_as_the_policy_script(self):
        control = (ROOT / 'scripts/iso/build-local-packages.sh').read_text(encoding='utf-8')
        self.assertIn('usr/lib/spaced-linux',
                      control.split('SETTINGS_PATHS=(')[1].split(')\n')[0])
        postinst = (ROOT / 'packages/spaced-mate-default-settings/DEBIAN/postinst').read_text()
        self.assertIn(GUARD_TARGET, postinst)
        self.assertIn('/usr/sbin/policy-rc.d', postinst)


if __name__ == '__main__':
    unittest.main()
