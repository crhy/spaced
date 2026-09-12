"""Display policy regressions without a live X server or session bus."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / 'overlays/usr/local/bin'


class DisplayPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)
        self.fakebin = self.state / 'bin'
        self.fakebin.mkdir()
        self.config = self.state / 'config'
        self.saved = self.config / 'spaced/screensaver-idle-activation'
        self.env = dict(os.environ, HOME=str(self.state),
                        XDG_CONFIG_HOME=str(self.config), DISPLAY=':spaced-test',
                        TEST_STATE=str(self.state),
                        PATH=f'{self.fakebin}:/usr/bin:/bin')
        self.write('schemas', 'org.mate.power-manager\norg.mate.screensaver\n')
        self.write('timeout', 'uint32 0\n')
        self.write('idle', 'true\n')
        self.command('xrandr', 'exit 0')
        self.command('xset', 'printf "%s\\n" "$*" >> "$TEST_STATE/xset-writes"')
        self.command('gsettings', '''case "$1" in
  list-schemas) cat "$TEST_STATE/schemas" ;;
  get)
    [ ! -e "$TEST_STATE/get-failure" ] || exit 1
    case "$2 $3" in
      "org.mate.power-manager sleep-display-"*) cat "$TEST_STATE/timeout" ;;
      "org.mate.screensaver idle-activation-enabled") cat "$TEST_STATE/idle" ;;
      *) exit 1 ;;
    esac ;;
  set)
    printf '%s\\n' "$*" >> "$TEST_STATE/settings-writes"
    [ ! -e "$TEST_STATE/set-failure" ] || exit 1
    [ "$2 $3" = 'org.mate.screensaver idle-activation-enabled' ] || exit 1
    printf '%s\\n' "$4" > "$TEST_STATE/idle" ;;
  *) exit 1 ;;
esac''')

    def write(self, name, value):
        (self.state / name).write_text(value)

    def command(self, name, body):
        executable = self.fakebin / name
        executable.write_text(f'#!/bin/bash\n{body}\n')
        executable.chmod(0o755)

    def run_helper(self, name='spaced-display-repair'):
        result = subprocess.run([str(BIN / name)], env=self.env,
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def writes(self, name='settings-writes'):
        path = self.state / name
        return path.read_text().splitlines() if path.exists() else []

    def test_never_suppresses_idle_without_changing_lock_or_session_delay(self):
        self.run_helper()
        self.assertEqual(self.writes(), ['set org.mate.screensaver idle-activation-enabled false'])
        self.assertEqual(self.saved.read_text(), 'true\n')
        self.assertEqual(self.writes('xset-writes'), ['-dpms', 's off', 's noblank'])

    def test_repeated_login_retains_original_preference_then_restores_once(self):
        self.run_helper()
        self.run_helper()
        self.assertEqual(self.saved.read_text(), 'true\n')
        self.assertEqual(len(self.writes()), 1)
        self.write('timeout', '1800\n')
        self.run_helper()
        self.run_helper()
        self.assertEqual(self.writes(), [
            'set org.mate.screensaver idle-activation-enabled false',
            'set org.mate.screensaver idle-activation-enabled true'])
        self.assertFalse(self.saved.exists())
        self.assertEqual(self.writes('xset-writes')[-2:], ['+dpms', '+dpms'])

    def test_previously_disabled_idle_stays_disabled(self):
        self.write('idle', 'false\n')
        self.run_helper()
        self.write('timeout', 'uint32 1800\n')
        self.run_helper()
        self.assertFalse(self.saved.exists())
        self.assertEqual(self.writes(), [])

    def test_positive_timeout_without_saved_state_preserves_screensaver(self):
        self.write('timeout', 'uint32 1800\n')
        self.run_helper()
        self.assertEqual(self.writes(), [])
        self.assertEqual(self.writes('xset-writes'), ['+dpms'])

    def test_missing_screensaver_schema_still_applies_dpms(self):
        self.write('schemas', 'org.mate.power-manager\n')
        self.run_helper()
        self.assertEqual(self.writes(), [])
        self.assertFalse(self.saved.exists())
        self.assertEqual(self.writes('xset-writes'), ['-dpms', 's off', 's noblank'])

    def test_invalid_timeout_never_disables_idle_or_dpms(self):
        for value in ['', 'unknown', 'uint32 bogus', '-1', 'uint32 0 garbage']:
            with self.subTest(value=value):
                self.write('timeout', value)
                self.run_helper()
                self.assertEqual(self.writes(), [])
                self.assertEqual(self.writes('xset-writes'), [])

    def test_failed_settings_read_is_not_treated_as_never(self):
        self.write('get-failure', '')
        self.run_helper()
        self.assertEqual(self.writes(), [])
        self.assertEqual(self.writes('xset-writes'), [])

    def test_invalid_idle_preference_is_not_overwritten(self):
        self.write('idle', 'unavailable\n')
        self.run_helper()
        self.assertEqual(self.writes(), [])
        self.assertFalse(self.saved.exists())

    def test_failed_state_save_does_not_disable_idle(self):
        self.saved.mkdir(parents=True)
        self.run_helper()
        self.assertEqual(self.writes(), [])

    def test_failed_restore_retains_state_for_retry(self):
        self.run_helper()
        self.write('timeout', 'uint32 1800\n')
        self.write('set-failure', '')
        self.run_helper()
        self.assertEqual(self.saved.read_text(), 'true\n')
        (self.state / 'set-failure').unlink()
        self.run_helper()
        self.assertFalse(self.saved.exists())
        self.assertEqual((self.state / 'idle').read_text(), 'true\n')

    def test_invalid_saved_preference_cannot_enable_idle(self):
        self.saved.parent.mkdir(parents=True)
        self.saved.write_text('not-a-boolean\n')
        self.write('idle', 'false\n')
        self.write('timeout', '1800\n')
        self.run_helper()
        self.assertEqual(self.writes(), [])

    def test_watch_mode_periodically_reconciles_driver_dpms_changes(self):
        helper = (BIN / 'spaced-display-repair').read_text()
        self.assertIn('while sleep 30; do', helper)
        self.assertIn('apply_power_policy\n    done &', helper)

    def test_first_login_does_not_override_auto_or_explicit_scaling(self):
        self.command('python3', 'exit 0')
        self.command('xdpyinfo', 'echo invoked >> "$TEST_STATE/dpi-reads"; echo "resolution: 96x96 dots per inch"')
        self.write('schemas', 'org.mate.interface\n')
        marker = self.state / '.config/spaced/first-login-repair-v5'
        for value in ['0', '1', '2']:
            with self.subTest(scale=value):
                self.write('scale', value)
                self.run_helper('spaced-first-login-repair')
                self.assertEqual((self.state / 'scale').read_text(), value)
                self.assertEqual(self.writes(), [])
                self.assertEqual(self.writes('dpi-reads'), [])
                marker.unlink()

    def test_graphics_report_collects_policy_without_writes(self):
        self.command('timeout', 'printf "%s\\n" "${*:3}" >> "$TEST_STATE/report-commands"')
        for command in ['uname', 'cat', 'lspci', 'lsusb', 'lsmod', 'glxinfo',
                        'xdpyinfo', 'xrdb', 'xprop', 'ps', 'dpkg-query', 'mokutil',
                        'nvidia-smi', 'env', 'dkms', 'dmesg']:
            self.command(command, 'exit 0')
        self.run_helper('spaced-graphics-report')
        commands = self.writes('report-commands')
        for schema in ['interface', 'font-rendering', 'power-manager', 'session', 'screensaver']:
            self.assertIn(f'gsettings list-recursively org.mate.{schema}', commands)
        self.assertIn('xset q', commands)
        self.assertIn('xrdb -query', commands)
        self.assertIn('xrandr --verbose', commands)
        self.assertEqual(self.writes(), [])


if __name__ == '__main__':
    unittest.main()
