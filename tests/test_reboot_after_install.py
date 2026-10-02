"""Issues #192 and #251: the post-install prompt must appear and restart."""
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'overlays/usr/local/bin/spaced-reboot-after-install'


def load_helper():
    # Bytecode beside the helper would leak into the image.
    sys.dont_write_bytecode = True
    loader = importlib.machinery.SourceFileLoader('spaced_reboot_after_install', str(HELPER))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


DRIVER = textwrap.dedent('''
    import importlib.machinery, importlib.util, sys
    sys.dont_write_bytecode = True
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import GLib, Gtk
    loader = importlib.machinery.SourceFileLoader('helper', sys.argv[1])
    spec = importlib.util.spec_from_loader(loader.name, loader)
    helper = importlib.util.module_from_spec(spec)
    loader.exec_module(helper)

    def restarted():
        print('RESTART', flush=True)
        Gtk.main_quit()

    GLib.timeout_add_seconds(15, lambda: sys.exit('prompt never restarted'))
    print('SHOWN', flush=True)
    helper.show_prompt(restarted)
''')


@unittest.skipUnless(shutil.which('Xvfb') and shutil.which('xdotool'), 'needs Xvfb and xdotool')
class PromptTests(unittest.TestCase):
    def run_prompt(self, action):
        with tempfile.TemporaryDirectory() as temp:
            driver = Path(temp) / 'driver.py'
            driver.write_text(DRIVER)
            # No window manager runs, which matches the prompt's real situation
            # after the live desktop has been closed.
            script = (f'python3 {driver} {HELPER} & app=$!; sleep 2; '
                      f'{action}; wait $app')
            result = subprocess.run(
                ['xvfb-run', '-a', '-s', '-screen 0 1024x768x24', 'bash', '-c', script],
                capture_output=True, text=True, timeout=60,
                env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('RESTART', result.stdout, result.stderr)

    def test_key_press_restarts_without_window_manager(self):
        self.run_prompt('xdotool key space')

    def test_click_restarts(self):
        self.run_prompt('xdotool mousemove 512 384 click 1')


class RebootFallbackTests(unittest.TestCase):
    def test_prompt_failure_still_reboots(self):
        helper = load_helper()
        with mock.patch.object(helper, 'close_live_desktop'), \
                mock.patch.object(helper, 'show_prompt', side_effect=RuntimeError('no display')), \
                mock.patch.object(helper, 'reboot') as reboot:
            helper.main()
        reboot.assert_called_once_with()

    def test_desktop_closes_before_prompt(self):
        helper = load_helper()
        order = []
        with mock.patch.object(helper, 'close_live_desktop', lambda: order.append('close')), \
                mock.patch.object(helper, 'show_prompt', lambda _cb: order.append('prompt')), \
                mock.patch.object(helper, 'reboot', lambda: order.append('reboot')):
            helper.main()
        self.assertEqual(order, ['close', 'prompt', 'reboot'])

    def test_live_desktop_is_closed_by_owner_not_by_name(self):
        helper = load_helper()
        live, root = 1000, 0
        processes = [
            (1, 0, root, 'init'),
            (400, 1, root, 'Xorg'),
            (500, 1, root, 'lightdm'),
            (900, 500, live, 'mate-session'),
            (901, 900, live, 'mate-panel'),
            # The kernel truncates names to 15 characters, which defeated
            # `pkill -x mate-notification-daemon` and friends.
            (902, 900, live, 'mate-notificati'),
            (903, 900, live, 'spaced-window-m'),
            (904, 903, live, 'compiz'),
            (905, 900, live, 'nm-applet'),
            (906, 900, live, 'install-spaced-'),
            (907, 906, root, 'sudo'),
            (908, 907, root, 'calamares'),
            (909, 908, root, 'sh'),
            (910, 909, root, 'python3'),
            (920, 1, 1001, 'mate-panel'),
        ]
        sessions, victims = helper.desktop_targets(processes, own_pid=910)
        self.assertEqual(sessions, [900])
        # The installer chain above the helper survives; root and other
        # users' processes are never touched.
        self.assertEqual(sorted(victims), [901, 902, 903, 904, 905])

    def test_no_session_means_nothing_is_killed(self):
        helper = load_helper()
        processes = [(1, 0, 0, 'init'), (50, 1, 1000, 'bash'), (60, 50, 0, 'python3')]
        self.assertEqual(helper.desktop_targets(processes, own_pid=60), ([], []))

    def test_process_list_includes_this_process(self):
        helper = load_helper()
        own = [p for p in helper.list_processes() if p[0] == os.getpid()]
        self.assertEqual(len(own), 1)
        self.assertEqual(own[0][1], os.getppid())
        self.assertEqual(own[0][2], os.getuid())

    def test_clean_restart_comes_before_emergency_restart(self):
        # A sysrq restart skips device shutdown; a laptop then reported "No
        # bootable device" until it was power-cycled.
        helper = load_helper()
        calls = []
        with mock.patch.object(helper.os, 'sync', lambda: calls.append('sync')), \
                mock.patch.object(helper, 'LIBC') as libc, \
                mock.patch('builtins.open', mock.mock_open()) as sysrq, \
                mock.patch.object(helper.subprocess, 'run'):
            libc.reboot.side_effect = lambda _cmd: calls.append('reboot syscall')
            sysrq.side_effect = lambda *_args, **_kwargs: calls.append('sysrq') or mock.mock_open()()
            helper.reboot()
        self.assertEqual(calls[:3], ['sync', 'reboot syscall', 'sysrq'])
        libc.reboot.assert_called_once_with(0x01234567)

    def test_helper_is_executable(self):
        self.assertTrue(os.access(HELPER, os.X_OK))


if __name__ == '__main__':
    unittest.main()
