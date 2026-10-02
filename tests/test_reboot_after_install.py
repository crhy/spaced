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

    def test_helper_is_executable(self):
        self.assertTrue(os.access(HELPER, os.X_OK))


if __name__ == '__main__':
    unittest.main()
