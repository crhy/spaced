"""Issue #202: exercise output persistence without an audio server."""
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'overlays/usr/local/bin/spaced-audio-restore'


class AudioRestoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / 'config/spaced/audio-state'
        self.state.parent.mkdir(parents=True)
        self.commands = self.root / 'commands'
        self.default = self.root / 'default'
        self.default.write_text('speakers\n')
        (self.root / 'sinks').write_text('speakers\nheadphones\n')
        self.env = dict(os.environ, HOME=str(self.root),
                        XDG_CONFIG_HOME=str(self.root / 'config'),
                        TEST_STATE=str(self.root),
                        SPACED_AUDIO_SETTLE_SECONDS='0.05',
                        PATH=str(self.root) + os.pathsep + os.environ['PATH'])
        pactl = self.root / 'pactl'
        pactl.write_text('''#!/bin/bash
[ "$LC_ALL" = C ] || exit 1
case "$1" in
    info) exit 0 ;;
    get-default-sink) cat "$TEST_STATE/default" ;;
    get-sink-volume)
        [ "${FAIL_READ:-0}" = 0 ] || exit 1
        printf 'Volume: front-left: 32768 / %s%% / -18.06 dB\\n' "${VOLUME:-50}" ;;
    get-sink-mute) printf 'Mute: %s\\n' "${MUTE:-no}" ;;
    set-default-sink)
        printf '%s\\n' "$*" >> "$TEST_STATE/commands"
        grep -Fxq -- "$2" "$TEST_STATE/sinks" || exit 1
        printf '%s\\n' "$2" > "$TEST_STATE/default" ;;
    set-sink-volume|set-sink-mute)
        printf '%s\\n' "$*" >> "$TEST_STATE/commands" ;;
    subscribe)
        if [ -n "${NEXT_DEFAULT:-}" ]; then
            printf '%s\\n' "$NEXT_DEFAULT" > "$TEST_STATE/default"
        fi
        printf "Event 'change' on server #0\\n"
        printf "Event 'change' on sink #1\\n"
        if [ "${HOLD_SUBSCRIPTION:-0}" = 1 ]; then
            touch "$TEST_STATE/subscribed"
            sleep 0.5
        fi ;;
    *) exit 1 ;;
esac
''')
        pactl.chmod(0o755)

    def run_helper(self):
        result = subprocess.run([str(HELPER)], env=self.env, capture_output=True,
                                text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        return self.commands.read_text().splitlines() if self.commands.exists() else []

    def test_restore_named_sink_before_its_volume_and_mute(self):
        self.state.write_text('35 yes headphones\n')
        self.assertEqual(self.run_helper(), [
            'set-default-sink headphones',
            'set-sink-volume headphones 35%',
            'set-sink-mute headphones 1'])
        self.assertEqual(self.default.read_text(), 'headphones\n')
        self.assertEqual(self.state.read_text(), '50 no headphones\n')

    def test_legacy_volume_and_mute_are_migrated_without_changing_output(self):
        self.state.write_text('0 yes\n')
        self.assertEqual(self.run_helper(), [
            'set-sink-volume @DEFAULT_SINK@ 0%',
            'set-sink-mute @DEFAULT_SINK@ 1'])
        self.assertEqual(self.state.read_text(), '50 no speakers\n')

    def test_missing_sink_preserves_preference_and_leaves_fallback_untouched(self):
        self.state.write_text('85 no unplugged-usb\n')
        self.assertEqual(self.run_helper(), ['set-default-sink unplugged-usb'])
        self.assertEqual(self.state.read_text(), '85 no unplugged-usb\n')

    def test_new_selection_replaces_unavailable_preference(self):
        self.state.write_text('85 no unplugged-usb\n')
        self.env['NEXT_DEFAULT'] = 'headphones'
        self.assertEqual(self.run_helper(), ['set-default-sink unplugged-usb'])
        self.assertEqual(self.state.read_text(), '50 no headphones\n')

    def test_new_default_is_saved_and_restored_at_next_login(self):
        self.env['NEXT_DEFAULT'] = 'headphones'
        self.assertEqual(self.run_helper(), [])
        self.assertEqual(self.state.read_text(), '50 no headphones\n')
        del self.env['NEXT_DEFAULT']
        self.default.write_text('speakers\n')
        self.assertEqual(self.run_helper()[0], 'set-default-sink headphones')
        self.assertEqual(self.default.read_text(), 'headphones\n')

    def test_saved_zero_volume_and_mute_remain_intentional(self):
        self.state.write_text('0 yes headphones\n')
        self.env.update(VOLUME='0', MUTE='yes')
        self.assertEqual(self.run_helper(), [
            'set-default-sink headphones',
            'set-sink-volume headphones 0%',
            'set-sink-mute headphones 1'])
        self.assertEqual(self.state.read_text(), '0 yes headphones\n')

    def test_logout_signal_flushes_selection_before_debounce(self):
        self.env.update(NEXT_DEFAULT='headphones', HOLD_SUBSCRIPTION='1',
                        SPACED_AUDIO_SETTLE_SECONDS='10')
        process = subprocess.Popen([str(HELPER)], env=self.env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 3
            while not (self.root / 'subscribed').exists():
                self.assertLess(time.monotonic(), deadline, 'subscription did not start')
                time.sleep(0.01)
            self.assertEqual(self.state.read_text(), '50 no speakers\n')
            process.terminate()
            stdout, stderr = process.communicate(timeout=3)
            self.assertEqual(process.returncode, 0, stderr)
            self.assertEqual(self.state.read_text(), '50 no headphones\n')
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()

    def test_dummy_fallback_cannot_overwrite_real_output(self):
        self.state.write_text('50 no headphones\n')
        self.env['NEXT_DEFAULT'] = 'auto_null'
        self.run_helper()
        self.assertEqual(self.state.read_text(), '50 no headphones\n')

    def test_failed_query_cannot_truncate_saved_state(self):
        self.state.write_text('50 no headphones\n')
        self.env['FAIL_READ'] = '1'
        self.run_helper()
        self.assertEqual(self.state.read_text(), '50 no headphones\n')

    def test_corrupt_state_is_not_executed_or_sent_to_pactl(self):
        self.state.write_text('$(touch injected) yes headphones\n')
        self.assertEqual(self.run_helper(), [])
        self.assertEqual(self.state.read_text(), '50 no speakers\n')
        self.assertFalse((self.root / 'injected').exists())


if __name__ == '__main__':
    unittest.main()
