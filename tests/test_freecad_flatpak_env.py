"""Exercise #425 migrations without changing the desktop's Flatpak state."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / 'overlays/usr/local/bin'
APP = 'org.freecad.FreeCAD'
RULE = 'qt.accessibility.atspi=false'


class FreecadEnvTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fake = self.root / 'flatpak'
        self.fake.write_text('''#!/bin/sh
printf '%s\\n' "$*" >> "$HOME/calls"
case "$*" in
  *--show*)
    [ "${READ_FAIL:-0}" = 0 ] || exit 1
    case "$*" in
      *--system*) printf '%s\\n' "${SYSTEM_OVERRIDE:-}" ;;
      *--user*) printf '%s\\n' "${USER_OVERRIDE:-}" ;;
    esac ;;
  *--env=*) exit "${WRITE_FAIL:-0}" ;;
esac
''')
        self.fake.chmod(0o755)
        self.env = dict(os.environ, HOME=str(self.root),
                        XDG_CONFIG_HOME=str(self.root / 'config'),
                        XDG_DATA_HOME=str(self.root / 'data'),
                        SPACED_FLATPAK_REAL=str(self.fake))
        self.env.pop('SPACED_APP_STATE_DIR', None)
        self.marker = self.root / 'config/spaced/freecad-flatpak-env-11.26.3'

    def run_helper(self, **extra):
        return subprocess.run(['bash', str(BIN / 'spaced-freecad-flatpak-env')],
                              env=dict(self.env, **extra), text=True,
                              capture_output=True, timeout=10)

    def calls(self):
        path = self.root / 'calls'
        return path.read_text().splitlines() if path.exists() else []

    def test_applies_scoped_rule_once_and_preserves_other_keys(self):
        result = self.run_helper(USER_OVERRIDE='[Context]\nfilesystems=home;\n'
                                 '[Environment]\nKEEP_ME=yes')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls(), [f'override --system --show {APP}',
                                      f'override --user --show {APP}',
                                      f'override --user --env=QT_LOGGING_RULES={RULE} {APP}'])
        self.assertTrue(self.marker.exists())
        self.run_helper()
        self.assertEqual(len(self.calls()), 3)

    def test_read_or_write_failure_retries(self):
        for variable in ('READ_FAIL', 'WRITE_FAIL'):
            with self.subTest(variable=variable):
                result = self.run_helper(**{variable: '1'})
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.marker.exists())
        self.assertEqual(self.run_helper().returncode, 0)
        self.assertTrue(self.marker.exists())

    def test_explicit_logging_preferences_are_not_replaced(self):
        for scope in ('SYSTEM_OVERRIDE', 'USER_OVERRIDE'):
            for value in ('', '*.debug=false', 'qt.accessibility.atspi=true'):
                with self.subTest(scope=scope, value=value):
                    result = self.run_helper(**{scope: '[Environment]\nQT_LOGGING_RULES=' + value})
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('keeping custom QT_LOGGING_RULES', result.stderr)
                    self.assertFalse(self.marker.exists())
        self.assertFalse(any('--env=' in call for call in self.calls()))

    def test_existing_correct_rule_is_accepted(self):
        result = self.run_helper(USER_OVERRIDE=f'[Environment]\nQT_LOGGING_RULES={RULE}')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.marker.exists())

    def test_dangling_override_symlink_is_not_followed(self):
        overrides = self.root / 'data/flatpak/overrides'
        overrides.mkdir(parents=True)
        target = self.root / 'missing-target'
        (overrides / APP).symlink_to(target)
        result = self.run_helper()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(target.exists())
        self.assertFalse(self.marker.exists())
        self.assertEqual(self.calls(), [])

    def test_missing_flatpak_remains_retryable(self):
        self.assertEqual(self.run_helper(SPACED_FLATPAK_REAL='/nonexistent/flatpak').returncode, 0)
        self.assertFalse(self.marker.exists())

    def test_install_wrapper_applies_freecad_only_after_success(self):
        wrapper = self.root / 'wrapper'
        wrapper.write_text((BIN / 'flatpak').read_text().replace(
            '/usr/local/bin/spaced-freecad-flatpak-env',
            str(BIN / 'spaced-freecad-flatpak-env')))
        result = subprocess.run(['bash', str(wrapper), 'install', APP],
                                env=self.env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls()[0], f'install {APP}')
        self.assertTrue(self.marker.exists())

    def test_existing_login_repair_marker_does_not_skip_migration(self):
        text = (BIN / 'spaced-first-login-repair').read_text()
        self.assertLess(text.index('/usr/local/bin/spaced-freecad-flatpak-env'),
                        text.index('[ -e "$marker" ]'))

    @unittest.skipUnless(Path('/usr/bin/flatpak').is_file(), 'real Flatpak unavailable')
    def test_real_flatpak_preserves_unrelated_overrides(self):
        # This changes only a disposable XDG_DATA_HOME, never the user's state.
        real = '/usr/bin/flatpak'
        env = dict(self.env, SPACED_FLATPAK_REAL=real)
        subprocess.run([real, 'override', '--user', '--env=KEEP_ME=yes',
                        '--filesystem=/tmp', APP], env=env, check=True,
                       capture_output=True, timeout=10)
        result = self.run_helper(SPACED_FLATPAK_REAL=real)
        self.assertEqual(result.returncode, 0, result.stderr)
        shown = subprocess.check_output([real, 'override', '--user', '--show', APP],
                                        env=env, text=True, timeout=10)
        self.assertIn('KEEP_ME=yes', shown)
        self.assertIn('/tmp;', shown)
        self.assertIn(f'QT_LOGGING_RULES={RULE}', shown)


if __name__ == '__main__':
    unittest.main()
