"""Argument and text checks for the issue #409 reboot-loop VM script.

These cases never start QEMU or request a real power action.
"""
from pathlib import Path
import subprocess
import re
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/vm/qemu/reboot-loop.sh'


class RebootLoopScriptTests(unittest.TestCase):
    def run_functions(self, names, body):
        source = SCRIPT.read_text(encoding='utf-8')
        functions = '\n'.join(
            re.search(r'^' + name + r'\(\) \{\n.*?^\}', source,
                      re.MULTILINE | re.DOTALL).group(0)
            for name in names)
        return subprocess.run(['bash', '-c', 'set -eu\n' + functions + '\n' + body],
                              text=True, capture_output=True, timeout=10)

    def test_only_two_valid_distinct_boot_ids_prove_reboot(self):
        old = '11111111-1111-1111-1111-111111111111'
        new = '22222222-2222-2222-2222-222222222222'
        for before, after, expected in ((old, new, 0), (old, old, 1),
                                        ('', new, 1), (old, '', 1),
                                        ('invalid', new, 1), (old, 'error', 1)):
            with self.subTest(before=before, after=after):
                result = self.run_functions(['valid_boot_id', 'boot_changed'],
                                           f"boot_changed '{before}' '{after}'")
                self.assertEqual(result.returncode, expected, result.stderr)

    def test_denied_user_request_never_retries_as_root(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_functions(['trigger_power_action'], f'''
guest_ssh() {{ echo "Error org.freedesktop.DBus.Error.AccessDenied: not authorized"; return 1; }}
if trigger_power_action Reboot '{directory}/trigger.log'; then exit 10; fi
test ! -e '{directory}/trigger.log.fallback'
test "$TRIGGER_METHOD" = 'dbus-send Manager.Reboot (user request failed)'
''')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_desktop_mode_requires_matching_activation_evidence(self):
        for output, status, expected in (
                ('DESKTOP_ACTION_SENT: Reboot via MATE dialog 12', 0, 0),
                ('DESKTOP_ACTION_SENT: Reboot via MATE dialog 12', 255, 0),
                ('DESKTOP_ACTION_SENT: PowerOff via MATE dialog 12', 0, 1),
                ('No unique MATE shutdown dialog', 1, 1),
                ('', 0, 1)):
            with self.subTest(output=output, status=status), tempfile.TemporaryDirectory() as directory:
                result = self.run_functions(['trigger_power_action'], f'''
TRIGGER_MODE=desktop
SCRIPT_DIR='{SCRIPT.parent}'
guest_ssh() {{
    [[ "$1" == *"su - user"* && "$1" == *"--disposable-live-vm Reboot"* ]] || exit 12
    cat >/dev/null
    echo '{output}'
    return {status}
}}
if trigger_power_action Reboot '{directory}/trigger.log'; then
    test {expected} = 0
else
    test {expected} = 1
fi
''')
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_desktop_helper_refuses_missing_opt_in_and_unknown_actions(self):
        helper = SCRIPT.parent / 'guest-desktop-power.sh'
        for args in ([], ['--disposable-live-vm', 'Logout']):
            result = subprocess.run(['bash', str(helper), *args], capture_output=True,
                                    text=True, timeout=5)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_desktop_helper_has_no_privileged_power_fallback_or_countdown(self):
        source = (SCRIPT.parent / 'guest-desktop-power.sh').read_text()
        self.assertIn('gsettings set org.mate.session logout-timeout 0', source)
        self.assertIn('gsettings set org.mate.session logout-timeout "$OLD_TIMEOUT"', source)
        self.assertIn('timeout 10 xdotool windowactivate', source)
        self.assertIn('org.gnome.SessionManager.IsSessionRunning', source)
        self.assertIn("grep -qx '(true,)'", source)
        self.assertLess(source.index('IsSessionRunning'), source.index('mate-session-save --shutdown-dialog'))
        self.assertIn('grep -qw boot=live /proc/cmdline', source)
        self.assertIn('grep -qw hypervisor /proc/cpuinfo', source)
        self.assertNotIn('/sbin/reboot', source)
        self.assertNotIn('dbus-send', source)
        self.assertNotIn('sudo ', source)

    def test_round_requires_changed_id_not_just_ssh_reconnection(self):
        old = '11111111-1111-1111-1111-111111111111'
        new = '22222222-2222-2222-2222-222222222222'
        for after, expected in ((old, 'no'), ('', 'no'), (new, 'yes')):
            with self.subTest(after=after):
                result = self.run_functions(
                    ['valid_boot_id', 'boot_changed', 'reboot_round'], f'''
OUT=/unused; REBOOT_TIMEOUT=1; FAILURES=0; PHASE=before
wait_for_ssh() {{ return 0; }}
read_boot_id() {{ if [ "$PHASE" = before ]; then echo '{old}'; else echo '{after}'; fi; }}
read_elogind_version() {{ echo test; }}
start_dmesg_capture() {{ :; }}
stop_dmesg_capture() {{ :; }}
wait_for_user_session() {{ return 0; }}
trigger_power_action() {{ PHASE=after; }}
report_round() {{ test "$5" = '{expected}' || exit 12; }}
if reboot_round 1; then test '{expected}' = yes; else test '{expected}' = no; fi
''')
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def run_script(self, *args):
        return subprocess.run(['bash', str(SCRIPT), *args], text=True,
                              capture_output=True, timeout=30)

    def test_script_exists_and_parses(self):
        self.assertTrue(SCRIPT.is_file(), f'missing {SCRIPT}')
        result = subprocess.run(['bash', '-n', str(SCRIPT)], text=True,
                                capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_usage_without_arguments(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 2)
        self.assertIn('Usage: reboot-loop.sh ISO [ROUNDS=5]',
                      result.stdout + result.stderr)

    def test_rejects_bad_round_count_and_missing_iso_without_booting(self):
        for args in (['/dev/null', '0'], ['/dev/null', 'many'], ['missing.iso', '3']):
            with self.subTest(args=args):
                result = self.run_script(*args)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertNotIn('QEMU PID', result.stdout)

    def test_guest_reboots_are_not_disabled(self):
        """A -no-reboot guest can never show the crash or a real reboot."""
        text = SCRIPT.read_text(encoding='utf-8')
        self.assertNotIn('-no-reboot', text)
        self.assertIn('-boot order=d', text)
        self.assertIn('org.freedesktop.login1.Manager.Reboot', text)
        self.assertIn('org.freedesktop.login1.Manager.PowerOff', text)

    def test_cleanup_kills_only_recorded_processes(self):
        text = SCRIPT.read_text(encoding='utf-8')
        self.assertNotIn('pkill -f', text)
        self.assertIn('trap cleanup EXIT', text)
        self.assertIn('QEMU_PID=$!', text)


if __name__ == '__main__':
    unittest.main()
