"""The Orca Slicer Flatpak needs its WebKit overrides out of the box (#423).

Only com.orcaslicer.OrcaSlicer may receive the two variables, the one-time
migration must not repeat forever when the override fails (docs/ROADMAP.md
a02-13), and an Orca installed in the current session must be fixed without
waiting for the next login.
"""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / 'overlays/usr/local/bin'
HELPER = BIN / 'spaced-flatpak-app-env'
APP_ID = 'com.orcaslicer.OrcaSlicer'
OVERRIDE = (f'override --user --env=WEBKIT_DISABLE_COMPOSITING_MODE=1'
            f' --env=WEBKIT_DISABLE_DMABUF_RENDERER=1 {APP_ID}')


class OrcaFlatpakEnvTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)
        self.bindir = self.state / 'bin'
        self.bindir.mkdir()
        self.config = self.state / 'config'
        self.marker = self.config / 'spaced/flatpak-app-env-11.26.3'
        # A fake flatpak that records its arguments and obeys FAIL, plus a
        # logger stand-in so a single failure report is observable offline.
        self.fake_flatpak = self.bindir / 'flatpak'
        self.fake_flatpak.write_text(
            '#!/bin/sh\nprintf "%s\\n" "$*" >> "$HOME/calls"\nexit "${FAIL:-0}"\n')
        self.fake_flatpak.chmod(0o755)
        (self.bindir / 'logger').write_text(
            '#!/bin/sh\nprintf "%s\\n" "$*" >> "$HOME/log-lines"\n')
        (self.bindir / 'logger').chmod(0o755)
        self.env = dict(os.environ, HOME=str(self.state),
                        XDG_CONFIG_HOME=str(self.config),
                        SPACED_FLATPAK_REAL=str(self.fake_flatpak),
                        PATH=str(self.bindir) + ':' + os.environ['PATH'])

    def calls(self, name='calls'):
        path = self.state / name
        return path.read_text().splitlines() if path.exists() else []

    def run_helper(self, extra=None):
        env = dict(self.env)
        env.update(extra or {})
        return subprocess.run(['bash', str(HELPER)], env=env,
                              capture_output=True, text=True, timeout=10)

    def run_wrapper(self, arguments):
        # The wrapper names the helper by its installed path; point that at the
        # overlay copy, exactly as the login-path tests rewrite their helpers.
        wrapper = self.state / 'flatpak-wrapper'
        wrapper.write_text((BIN / 'flatpak').read_text(encoding='utf-8').replace(
            '/usr/local/bin/spaced-flatpak-app-env', str(HELPER)))
        wrapper.chmod(0o755)
        return subprocess.run(['bash', str(wrapper), *arguments],
                              env=dict(self.env, SPACED_FLATPAK_REAL=str(self.fake_flatpak)),
                              capture_output=True, text=True, timeout=10)

    def run_login_repair(self):
        repair = self.state / 'spaced-first-login-repair'
        repair.write_text((BIN / 'spaced-first-login-repair').read_text(
            encoding='utf-8').replace(
            '/usr/local/bin/spaced-flatpak-app-env', str(HELPER)).replace(
            '/usr/local/bin/spaced-flatpak-theme-migration',
            str(self.bindir / 'theme-migration')))
        repair.chmod(0o755)
        (self.bindir / 'theme-migration').write_text('#!/bin/sh\nexit 0\n')
        (self.bindir / 'theme-migration').chmod(0o755)
        for tool in ('python3', 'gsettings'):
            stub = self.bindir / tool
            stub.write_text('#!/bin/sh\nexit 0\n')
            stub.chmod(0o755)
        return subprocess.run(['bash', str(repair)],
                              env=dict(self.env, SPACED_FLATPAK_REAL=str(self.fake_flatpak)),
                              capture_output=True, text=True, timeout=10)

    def test_both_variables_are_set_for_orca_only(self):
        result = self.run_helper()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls(), [OVERRIDE])
        for variable in ('WEBKIT_DISABLE_COMPOSITING_MODE=1',
                         'WEBKIT_DISABLE_DMABUF_RENDERER=1'):
            self.assertIn(variable, self.calls()[0])
        self.assertEqual({line.split()[-1] for line in self.calls()}, {APP_ID})
        self.assertTrue(self.marker.exists())

    def test_a_second_login_does_not_repeat_the_call(self):
        self.run_helper()
        second = self.run_helper()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(self.calls(), [OVERRIDE])

    def test_a_failing_override_still_leaves_the_marker(self):
        result = self.run_helper({'FAIL': '1'})
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.marker.exists(), 'the migration will repeat forever')
        self.assertEqual(len(self.calls()), 1)
        self.assertEqual(len(self.calls('log-lines')), 1, 'the failure is not reported')
        self.run_helper()
        self.assertEqual(self.calls(), [OVERRIDE])

    def test_a_machine_without_flatpak_exits_cleanly(self):
        result = self.run_helper({'SPACED_FLATPAK_REAL': str(self.state / 'no-flatpak')})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        self.assertEqual(self.calls(), [])
        self.assertFalse(self.marker.exists(), 'a later login cannot apply the fix')

    def test_the_marker_directory_can_be_redirected(self):
        state = self.state / 'app-state'
        result = self.run_helper({'SPACED_APP_STATE_DIR': str(state)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((state / 'flatpak-app-env-11.26.3').exists())
        self.assertFalse(self.marker.exists())
        self.assertEqual(self.calls(), [OVERRIDE])

    def test_login_runs_the_helper_before_its_own_marker_check(self):
        # An account that already finished first-login-repair-v5 still gets the
        # override, because the call sits above the marker check.
        (self.config / 'spaced').mkdir(parents=True)
        (self.config / 'spaced/first-login-repair-v5').touch()
        result = self.run_login_repair()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls(), [OVERRIDE])
        self.assertTrue(self.marker.exists())

    def test_installing_orca_fixes_it_in_the_same_session(self):
        result = self.run_wrapper(['install', APP_ID])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls(), [f'install {APP_ID}', OVERRIDE])
        self.assertTrue(self.marker.exists())

    def test_installing_another_app_touches_no_override(self):
        result = self.run_wrapper(['install', 'org.gimp.GIMP'])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls(), ['install org.gimp.GIMP'])
        self.assertFalse(self.marker.exists())


if __name__ == '__main__':
    unittest.main()
