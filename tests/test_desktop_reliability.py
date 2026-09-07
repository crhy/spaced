"""Behavioral regression tests; no running desktop or privileged writes."""
import configparser
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
BIN = ROOT / 'overlays/usr/local/bin'
spec = importlib.util.spec_from_file_location('migration', ROOT / 'overlays/usr/lib/spaced-linux/migrate-desktop.py')
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = Path(self.temp.name)

    def test_upgrade_preserves_custom_choices_and_is_idempotent(self):
        mime = self.config / 'mimeapps.list'
        mime.write_text('[Default Applications]\nimage/png=com.brave.Browser.desktop\nimage/jpeg=gimp.desktop\ntext/plain=custom-editor.desktop\nx-scheme-handler/https=firefox.desktop\n')
        profile = self.config / 'compiz/compizconfig/Default.ini'
        profile.parent.mkdir(parents=True)
        profile.write_text('[core]\nas_active_plugins=core;ccp;commands;decoration;\n[decoration]\nas_command=gtk-window-decorator --replace\n[commands]\nas_command0=my-custom-command\nas_run_command0_key=<Control>F8\n')
        original = profile.read_text()
        migration.migrate(self.config)
        actual = migration.read_ini(mime)['Default Applications']
        self.assertEqual(actual['image/png'], 'eom.desktop')
        self.assertEqual(actual['image/jpeg'], 'gimp.desktop')
        self.assertEqual(actual['text/plain'], 'custom-editor.desktop')
        self.assertEqual(actual['x-scheme-handler/https'], 'firefox.desktop')
        updated = migration.read_ini(profile)
        self.assertEqual(updated['decoration']['as_command'], 'spaced-window-decorator')
        self.assertEqual(updated['commands']['as_command0'], 'my-custom-command')
        self.assertEqual(updated['commands']['as_command1'], 'mate-screenshot --area')
        self.assertEqual(updated['commands']['as_run_command1_key'], '<Shift>Print')
        self.assertEqual(profile.with_name('Default.ini.pre-9.26').read_text(), original)
        files = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.config.rglob('*') if p.is_file()}
        migration.migrate(self.config)
        for p, state in files.items():
            self.assertEqual((p.read_bytes(), p.stat().st_mtime_ns), state)

    def test_custom_decorator_shortcut_and_btop_survive(self):
        profile = self.config / 'compiz/compizconfig/Default.ini'
        profile.parent.mkdir(parents=True)
        profile.write_text('[decoration]\nas_command=emerald --replace\n[screenshot]\nas_initiate_button=<Alt>Button2\n[commands]\nas_command3=custom-shot\nas_run_command3_key=<Shift>Print\n')
        btop = self.config / 'btop/btop.conf'
        btop.parent.mkdir()
        btop.write_text('graph_symbol = "braille"\n')
        migration.migrate(self.config)
        updated = migration.read_ini(profile)
        self.assertEqual(updated['decoration']['as_command'], 'emerald --replace')
        self.assertEqual(updated['screenshot']['as_initiate_button'], '<Alt>Button2')
        self.assertNotIn('as_command0', updated['commands'])
        self.assertEqual(btop.read_text(), 'graph_symbol = "braille"\n')

    def test_broken_configuration_is_preserved_and_retried(self):
        mime = self.config / 'mimeapps.list'
        mime.write_text('not an ini file\n')
        with self.assertRaises(configparser.Error):
            migration.migrate(self.config)
        self.assertEqual(mime.read_text(), 'not an ini file\n')
        self.assertFalse((self.config / 'spaced/desktop-migration-9.26-v1').exists())

    def test_mate_specific_defaults_are_migrated(self):
        mime = self.config / 'mate-mimeapps.list'
        mime.write_text('[Default Applications]\nimage/png=firefox.desktop\nimage/tiff=gimp.desktop\n')
        migration.migrate(self.config)
        defaults = migration.read_ini(mime)['Default Applications']
        self.assertEqual(defaults['image/png'], 'eom.desktop')
        self.assertEqual(defaults['image/tiff'], 'gimp.desktop')


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)
        self.fakebin = self.state / 'bin'
        self.fakebin.mkdir()
        self.env = dict(os.environ, HOME=str(self.state), XDG_RUNTIME_DIR=str(self.state),
                        DISPLAY=':spaced-test', TEST_STATE=str(self.state),
                        PATH=str(self.fakebin) + os.pathsep + os.environ['PATH'])
        self.command('logger', 'exit 0')
        self.command('xprop', 'exit "${XPROP_STATUS:-0}"')
        self.command('glxinfo', "printf 'direct rendering: Yes\\nOpenGL renderer string: test\\n'")
        self.command('sleep', 'printf "%s\\n" "$1" >> "$TEST_STATE/delays"')

    def command(self, name, body):
        path = self.fakebin / name
        path.write_text('#!/bin/bash\n' + body + '\n')
        path.chmod(0o755)

    def crash_program(self, name, failures):
        self.command(name, 'n=$(cat "$TEST_STATE/count" 2>/dev/null || echo 0)\n'
                           'n=$((n+1))\necho "$n" > "$TEST_STATE/count"\n'
                           f'[ "$n" -gt {failures} ] && exit 0\nexit 139')

    def run_helper(self, name):
        return subprocess.run([str(BIN / name)], env=self.env, capture_output=True, text=True, timeout=5)

    def test_compiz_recovers_with_capped_backoff(self):
        self.crash_program('compiz', 7)
        self.assertEqual(self.run_helper('spaced-window-manager').returncode, 0)
        self.assertEqual((self.state / 'count').read_text().strip(), '8')
        self.assertEqual((self.state / 'delays').read_text().splitlines(), ['1', '2', '4', '8', '16', '30', '30'])

    def test_decorator_crash_recovers_without_restarting_compiz(self):
        self.crash_program('gtk-window-decorator', 1)
        self.assertEqual(self.run_helper('spaced-window-decorator').returncode, 0)
        self.assertEqual((self.state / 'count').read_text().strip(), '2')

    def test_x_server_exit_does_not_respawn(self):
        for helper, binary in [('spaced-window-manager', 'compiz'), ('spaced-window-decorator', 'gtk-window-decorator')]:
            with self.subTest(helper=helper):
                (self.state / 'count').unlink(missing_ok=True)
                self.crash_program(binary, 9)
                self.env['XPROP_STATUS'] = '1'
                self.assertEqual(self.run_helper(helper).returncode, 139)
                self.assertEqual((self.state / 'count').read_text().strip(), '1')
                self.assertFalse((self.state / 'delays').exists())

    def test_clean_decorator_replacement_does_not_restart(self):
        self.crash_program('gtk-window-decorator', 0)
        self.assertEqual(self.run_helper('spaced-window-decorator').returncode, 0)
        self.assertEqual((self.state / 'count').read_text().strip(), '1')
        self.assertFalse((self.state / 'delays').exists())

    def test_display_repair_preserves_modes_and_disabled_dpms(self):
        # Two active 4K outputs with multiple refresh rates and non-row positions;
        # connected but disabled output and a disconnected output must stay off.
        (self.state / 'xrandr').write_text('''Screen 0: minimum 8 x 8, current 7680 x 4320, maximum 16384 x 16384
DP-0 connected primary 3840x2160+0+2160 (normal left inverted right x axis y axis)
    underscan: on
    underscan hborder: 25
    underscan vborder: 18
    Broadcast RGB: Automatic
   3840x2160 60.00 + 59.94* 30.00
DP-1 connected 3840x2160+3840+0 (normal left inverted right x axis y axis)
    underscan: off
    underscan hborder: 0
    underscan vborder: 0
   3840x2160 60.00 + 30.00*
HDMI-1 connected (normal left inverted right x axis y axis)
    underscan: on
HDMI-2 disconnected (normal left inverted right x axis y axis)
    underscan: on
''')
        self.command('xrandr', 'if [ "$*" = --prop ]; then cat "$TEST_STATE/xrandr"; else printf "%s\\n" "$*" >> "$TEST_STATE/display-writes"; fi')
        self.command('xset', 'printf "%s\\n" "$*" >> "$TEST_STATE/power-writes"')
        self.assertEqual(self.run_helper('spaced-display-repair').returncode, 0)
        self.assertEqual((self.state / 'display-writes').read_text().splitlines(), [
            '--output DP-0 --set underscan off', '--output DP-0 --set underscan hborder 0',
            '--output DP-0 --set underscan vborder 0'])
        self.assertFalse((self.state / 'power-writes').exists())


if __name__ == '__main__':
    unittest.main()
