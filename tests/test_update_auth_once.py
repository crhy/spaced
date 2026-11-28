"""crhy/spacedupdate#19: a full update run authenticates exactly once.

A fake pkexec/sudo on PATH counts every invocation. The admin (com.spacedlinux
.update) steps of a full run - apt-install, system flatpak-update, the full
system update (which does apt + flatpak + firmware + GRUB repair in one helper
invocation) and cleanup - share one privilege session: exactly one pkexec, then
sudo -n for every later step. The read-only refresh stays a separate,
password-free pkexec (issue #277) and is not an admin authorisation. No real
pkexec, polkit or sudo runs here.
"""
from pathlib import Path
import importlib.util
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True

try:
    _spec = importlib.util.spec_from_file_location(
        'spaced_update_auth_once',
        ROOT / 'overlays/usr/lib/spaced-linux/spaced-update.py')
    spaced_update = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(spaced_update)
except Exception:
    spaced_update = None

HELPER = spaced_update.HELPER if spaced_update else ''
REFRESH_HELPER = spaced_update.REFRESH_HELPER if spaced_update else ''


FAKE = """#!/bin/bash
name=$(basename "$0")
printf '%s\\t%s\\n' "$name" "$*" >> "$UPDATE_LOG"
exit ${__EXITVAR__:-0}
"""


@unittest.skipIf(spaced_update is None, 'needs PyGObject/GTK')
class AuthOnceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.bin = base / 'bin'
        self.bin.mkdir()
        self.log = base / 'log'
        self.log.write_text('')
        os.environ['UPDATE_LOG'] = str(self.log)
        for tool, exit_var in (('pkexec', 'PKEXEC_EXIT'), ('sudo', 'SUDO_EXIT')):
            script = self.bin / tool
            script.write_text(FAKE.replace('__EXITVAR__', exit_var))
            script.chmod(script.stat().st_mode | stat.S_IEXEC)
        self.old_path = os.environ['PATH']
        os.environ['PATH'] = f'{self.bin}{os.pathsep}{self.old_path}'
        auth = spaced_update.AUTH_SESSION
        self.saved = dict(auth)
        auth.update({'authorised': False, 'closing': False, 'keepalive': None})
        # The keep-alive loop must not spawn a real background renewer here.
        self._keepalive = spaced_update._start_privileged_keepalive
        patcher = mock.patch.object(
            spaced_update, '_start_privileged_keepalive', lambda: None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        os.environ['PATH'] = self.old_path
        os.environ.pop('PKEXEC_EXIT', None)
        os.environ.pop('SUDO_EXIT', None)
        spaced_update.AUTH_SESSION.update(self.saved)

    def rows(self):
        return [line.split('\t') for line in self.log.read_text().splitlines() if line]

    def run_sequence(self):
        invoker = lambda command: spaced_update.run_capture(command, timeout=60)
        spaced_update.privileged([HELPER, 'apt-install', 'curl'], invoker)
        spaced_update.privileged(
            [HELPER, 'flatpak-update', '--system', 'app/io.github.crhy.rhYciv/x86_64/master'],
            invoker)
        # The full system update: one helper invocation does apt + flatpak +
        # firmware + GRUB repair (helper MODE=all).
        spaced_update.privileged([HELPER], invoker)
        spaced_update.privileged([HELPER, 'cleanup-plan'], invoker)
        spaced_update.privileged([HELPER, 'cleanup-apply'], invoker)

    def test_full_run_authorises_exactly_once(self):
        self.run_sequence()
        rows = self.rows()
        pkexecs = [r for r in rows if r and r[0] == 'pkexec']
        # Only one pkexec for the whole run, and it is the helper auth probe.
        self.assertEqual(len(pkexecs), 1)
        self.assertEqual(pkexecs[0][1].split()[-1], 'auth')
        self.assertEqual(pkexecs[0][1].split()[0], HELPER)
        # Every later admin step reused the cached credential via sudo -n.
        sudos = [r for r in rows if r and r[0] == 'sudo']
        self.assertEqual(len(sudos), 5)
        for row in sudos:
            self.assertEqual(row[1].split()[:3], ['-n', '--', HELPER])

    def test_cancelled_prompt_stops_cleanly(self):
        invoker = lambda command: spaced_update.run_capture(command, timeout=60)
        with mock.patch.object(
                spaced_update, 'run_capture',
                side_effect=RuntimeError(
                    'pkexec Authorization cancelled by user request; exited with status 126')):
            with self.assertRaises(spaced_update.UpdateCancelled):
                spaced_update.privileged([HELPER, 'apt-install', 'curl'], invoker)
        # A cancelled auth never runs the privileged command.
        self.assertEqual(self.rows(), [])
        self.assertFalse(spaced_update.AUTH_SESSION['authorised'])

    def test_refresh_is_a_separate_password_free_pkexec(self):
        # issue #277: the read-only refresh never opens the admin session.
        source = (ROOT / 'overlays/usr/lib/spaced-linux/spaced-update.py').read_text()
        self.assertIn('run_capture(["pkexec", REFRESH_HELPER]', source)

    def test_keepalive_is_bounded_and_terminates_with_the_window(self):
        started = []

        class _Proc:
            def __init__(self, command):
                self.command = command
                self.terminated = False

            def terminate(self):
                self.terminated = True

        def fake_popen(command, **kwargs):
            process = _Proc(command)
            started.append(process)
            return process

        with mock.patch.object(spaced_update.subprocess, 'Popen', side_effect=fake_popen):
            self._keepalive()
        process = started[0]
        script = process.command[-1]
        self.assertIn('sudo -n true', script)
        self.assertIn('86400', script)
        self.assertIn(f'kill -0 {os.getpid()}', script)
        spaced_update.AUTH_SESSION['keepalive'] = process
        spaced_update.AUTH_SESSION['authorised'] = True
        spaced_update.stop_privileged_keepalive()
        self.assertTrue(process.terminated)
        self.assertIsNone(spaced_update.AUTH_SESSION['keepalive'])
        self.assertFalse(spaced_update.AUTH_SESSION['authorised'])

    def test_helper_auth_probe_primes_sudo_once(self):
        # The shipped helper gained an `auth` mode: pkexec ran it as root, so it
        # primes the invoking user's sudo timestamp and exits before any lock.
        helper = ROOT / 'overlays/usr/lib/spaced-linux/spaced-update-helper'
        sudo_calls = self.bin / 'sudo'
        sudo_calls.write_text(
            '#!/bin/bash\nprintf "%s\\n" "$*" >> "$SUDO_LOG"\nexit 0\n')
        sudo_calls.chmod(sudo_calls.stat().st_mode | stat.S_IEXEC)
        sudo_log = Path(self.temp.name) / 'sudo-log'
        env = dict(os.environ)
        env['PATH'] = f'{self.bin}{os.pathsep}{self.old_path}'
        env['PKEXEC_UID'] = str(os.getuid())
        env['SUDO_LOG'] = str(sudo_log)
        result = subprocess.run(
            ['bash', str(helper), 'auth'], env=env,
            capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('-vk', sudo_log.read_text())


if __name__ == '__main__':
    unittest.main()
