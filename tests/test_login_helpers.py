"""Small login-path fixes (audit a02 rows).

a02-5: the "no Compiz" dialog in spaced-window-manager must never fork zenity
and mate-terminal back to back at full speed when both helpers fail at once.
a02-6: registering the signed Flatpak remotes must not ask the flatpak CLI the
same question twice per remote on every login.
"""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / 'overlays/usr/local/bin'


class NoCompizDialogLoopTests(unittest.TestCase):
    SENTINEL_GLOB = 'spaced-window-manager-no-compiz-*'

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)
        self.bindir = self.state / 'bin'
        self.bindir.mkdir()
        # An isolated PATH: no compiz (so the notice path runs) and only the
        # coreutils the notice path shells out to.
        for tool in ('id', 'sleep'):
            target = shutil.which(tool)
            self.assertIsNotNone(target, tool)
            os.symlink(target, self.bindir / tool)
        self.env = dict(os.environ, HOME=str(self.state),
                        XDG_RUNTIME_DIR=str(self.state),
                        DISPLAY=':spaced-test', TEST_STATE=str(self.state),
                        PATH=str(self.bindir))
        # Both helpers are GTK: with a dying X server zenity answers "Open
        # Terminal" and mate-terminal then fails instantly.
        self.stub('zenity', 'echo zenity >> "$TEST_STATE/zenity-calls"\nexit 1')
        self.stub('mate-terminal',
                  'echo terminal >> "$TEST_STATE/terminal-calls"\nexit 1')
        self.stub('logger', 'printf "%s\\n" "$*" >> "$TEST_STATE/logger-calls"')

    def stub(self, name, body):
        path = self.bindir / name
        path.write_text('#!/bin/bash\n' + body + '\n')
        path.chmod(0o755)

    def calls(self, name):
        path = self.state / name
        return path.read_text().splitlines() if path.exists() else []

    def test_failing_helpers_cannot_spin_the_dialog_loop(self):
        self.assertIsNone(shutil.which('compiz', path=str(self.bindir)))
        timeout = shutil.which('timeout')
        self.assertIsNotNone(timeout)
        result = subprocess.run(
            [timeout, '3', str(BIN / 'spaced-window-manager')], env=self.env,
            capture_output=True, text=True, timeout=15)
        # The session still has no window manager, so the choices keep being
        # offered after the three second observation window.
        self.assertEqual(result.returncode, 124, result.stderr)
        zenity = self.calls('zenity-calls')
        terminal = self.calls('terminal-calls')
        self.assertTrue(zenity, 'the dialog was never offered')
        self.assertTrue(terminal, 'the terminal choice was never handled')
        self.assertLess(len(zenity), 5, 'the dialog loop is spinning')
        self.assertLess(len(terminal), 5, 'the dialog loop is spinning')
        self.assertEqual(len(list(self.state.glob(self.SENTINEL_GLOB))), 1)
        self.assertEqual(len(self.calls('logger-calls')), 1)


class FlatpakRemoteCallTests(unittest.TestCase):
    """a02-6: both remotes already present must cost two flatpak calls, not
    four, and a machine that cannot add them must still keep retrying."""

    HELPER = BIN / 'spaced-enable-flatpak-remotes'

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)
        self.bindir = self.state / 'bin'
        self.bindir.mkdir()
        for tool in ('sleep', 'grep'):
            target = shutil.which(tool)
            self.assertIsNotNone(target, tool)
            os.symlink(target, self.bindir / tool)
        self.stub('logger', 'printf "%s\\n" "$*" >> "$TEST_STATE/logger-calls"')
        self.remotes = self.state / 'remotes'
        self.remotes.write_text('')
        flatpak = self.state / 'flatpak'
        flatpak.write_text('''#!/bin/bash
printf '%s\\n' "$*" >> "$TEST_STATE/flatpak-calls"
case "$1" in
    remotes)
        # Builtins only: the helper runs with a PATH that has no cat.
        while IFS= read -r line; do printf '%s\\n' "$line"; done \\
            < "$TEST_STATE/remotes" ;;
    remote-add)
        [ "${ADD_WORKS:-1}" = 1 ] || exit 1
        printf '%s\\n' "$4" >> "$TEST_STATE/remotes" ;;
    *) exit 1 ;;
esac
''')
        flatpak.chmod(0o755)
        # The helper names the flatpak binary absolutely; point it at the fake.
        helper = self.state / 'helper'
        helper.write_text(self.HELPER.read_text(encoding='utf-8').replace(
            'real_flatpak=/usr/bin/flatpak', f'real_flatpak={flatpak}'))
        helper.chmod(0o755)
        self.helper = helper
        self.env = dict(os.environ, HOME=str(self.state),
                        TEST_STATE=str(self.state), PATH=str(self.bindir))

    def stub(self, name, body):
        path = self.bindir / name
        path.write_text('#!/bin/bash\n' + body + '\n')
        path.chmod(0o755)

    def calls(self):
        path = self.state / 'flatpak-calls'
        return path.read_text().splitlines() if path.exists() else []

    def run_helper(self, extra=None, prefix=()):
        env = dict(self.env)
        if extra:
            env.update(extra)
        return subprocess.run([*prefix, str(self.helper)], env=env,
                              capture_output=True, text=True, timeout=15)

    def test_two_existing_remotes_cost_two_flatpak_calls(self):
        self.remotes.write_text('flathub\nspaced-github\n')
        result = self.run_helper()
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        self.assertLessEqual(len(calls), 2, f'login work regressed: {calls}')
        self.assertTrue(calls, 'the remotes were never checked')
        self.assertEqual({call.split()[0] for call in calls}, {'remotes'})

    def test_missing_remotes_are_registered_without_extra_queries(self):
        result = self.run_helper()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sorted(self.remotes.read_text().split()),
                         ['flathub', 'spaced-github'])
        calls = self.calls()
        self.assertEqual(sorted({call.split()[0] for call in calls}),
                         ['remote-add', 'remotes'])
        self.assertLessEqual(len(calls), 4, f'each remote is queried twice: {calls}')

    def test_unregistrable_remotes_keep_the_retry_loop_running(self):
        timeout = shutil.which('timeout')
        self.assertIsNotNone(timeout)
        result = self.run_helper({'ADD_WORKS': '0'}, prefix=(timeout, '3'))
        self.assertEqual(result.returncode, 124, result.stderr)
        self.assertEqual(self.remotes.read_text(), '')
        self.assertFalse((self.state / 'logger-calls').exists(),
                         'the retry loop gave up before its backoff window')


if __name__ == '__main__':
    unittest.main()
