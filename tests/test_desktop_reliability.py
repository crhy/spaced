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
        self.assertEqual(profile.with_name('Default.ini.pre-9.26.2').read_text(), original)
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

    def test_script_types_open_in_pluma_without_replacing_a_choice(self):
        # Issue #182: Pluma was never retained for bash and Python files
        # because those MIME types were not declared at all.
        mime = self.config / 'mimeapps.list'
        mime.write_text('[Default Applications]\ntext/x-python=custom-ide.desktop\n')
        migration.migrate(self.config)
        defaults = migration.read_ini(mime)['Default Applications']
        self.assertEqual(defaults['text/x-python'], 'custom-ide.desktop')
        for mime_type in ('text/x-python3', 'text/x-sh', 'application/x-sh',
                          'text/x-shellscript', 'application/x-shellscript',
                          'text/x-perl', 'application/x-perl', 'text/plain'):
            self.assertEqual(defaults[mime_type], 'pluma.desktop', mime_type)

    def test_mate_specific_defaults_are_migrated(self):
        mime = self.config / 'mate-mimeapps.list'
        mime.write_text('[Default Applications]\nimage/png=firefox.desktop\nimage/tiff=gimp.desktop\n')
        migration.migrate(self.config)
        defaults = migration.read_ini(mime)['Default Applications']
        self.assertEqual(defaults['image/png'], 'eom.desktop')
        self.assertEqual(defaults['image/tiff'], 'gimp.desktop')

    def test_mate_defaults_inherit_explicit_generic_choices(self):
        generic = self.config / 'mimeapps.list'
        generic.write_text('[Default Applications]\nimage/png=gimp.desktop\ntext/x-python=custom-ide.desktop\n')
        mate = self.config / 'mate-mimeapps.list'
        mate.write_text('[Default Applications]\n')
        migration.migrate(self.config)
        defaults = migration.read_ini(mate)['Default Applications']
        self.assertNotIn('image/png', defaults)
        self.assertNotIn('text/x-python', defaults)

    def test_v1_inserted_mate_defaults_are_removed(self):
        generic = self.config / 'mimeapps.list'
        generic.write_text('[Default Applications]\nimage/png=gimp.desktop\ntext/x-python=custom-ide.desktop\n')
        mate = self.config / 'mate-mimeapps.list'
        mate.write_text('[Default Applications]\nimage/png=eom.desktop\ntext/x-python=pluma.desktop\nimage/tiff=eom.desktop\n')
        mate.with_name('mate-mimeapps.list.pre-9.26.1').write_text(
            '[Default Applications]\nimage/tiff=eom.desktop\n')
        state = self.config / 'spaced'
        state.mkdir()
        (state / 'desktop-migration-9.26.1-v1').write_text('9.26.1\n')
        migration.migrate(self.config)
        defaults = migration.read_ini(mate)['Default Applications']
        self.assertNotIn('image/png', defaults)
        self.assertNotIn('text/x-python', defaults)
        self.assertEqual(defaults['image/tiff'], 'eom.desktop')


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
        self.fake_power_manager('1800')
        self.assertEqual(self.run_helper('spaced-display-repair').returncode, 0)
        self.assertEqual((self.state / 'display-writes').read_text().splitlines(), [
            '--output DP-0 --set underscan off', '--output DP-0 --set underscan hborder 0',
            '--output DP-0 --set underscan vborder 0'])
        # A real timeout leaves the schedule to mate-power-manager. Forcing the
        # outputs back on here would override the user's Power Management choice.
        self.assertEqual((self.state / 'power-writes').read_text().splitlines(), ['+dpms'])

    def fake_power_manager(self, timeout, mains_online=None):
        """Stand in for MATE's power schema and, optionally, an AC adapter."""
        self.command('gsettings',
                     'case "$1" in\n'
                     '  list-schemas) echo org.mate.power-manager ;;\n'
                     f'  get) echo "uint32 {timeout}" ;;\n'
                     'esac')
        if mains_online is not None:
            supply = self.state / 'power_supply' / 'AC0'
            supply.mkdir(parents=True, exist_ok=True)
            (supply / 'type').write_text('Mains\n')
            (supply / 'online').write_text(f'{mains_online}\n')

    def test_never_turn_off_display_disables_the_x_server_defaults(self):
        # Issue #178: MATE writes 0 for "Never" and then simply stops
        # programming a timeout, leaving the X server's own DPMS and blanking
        # defaults to power the monitors down anyway.
        (self.state / 'xrandr').write_text('Screen 0: current 1920 x 1080\n'
                                           'DP-0 connected primary 1920x1080+0+0\n')
        self.command('xrandr', 'if [ "$*" = --prop ]; then cat "$TEST_STATE/xrandr"; else exit 0; fi')
        self.command('xset', 'printf "%s\\n" "$*" >> "$TEST_STATE/power-writes"')
        self.fake_power_manager('0')
        self.assertEqual(self.run_helper('spaced-display-repair').returncode, 0)
        self.assertEqual((self.state / 'power-writes').read_text().splitlines(),
                         ['-dpms', 's off', 's noblank'])

    def test_audio_state_is_saved_once_per_burst_of_events(self):
        # Dragging the volume slider emits a stream of sink events. Saving on
        # each one spawned three pactl processes per event; the helper now
        # coalesces a burst into a single save.
        pactl = self.fakebin / 'pactl'
        pactl.write_text(
            "#!/bin/bash\n"
            "case \"$1\" in\n"
            "  info) exit 0 ;;\n"
            "  get-default-sink) echo spaced-test-sink ;;\n"
            "  get-sink-volume)\n"
            "    echo 'Volume: front-left: 32768 /  50% / -18.06 dB'\n"
            "    echo saved >> \"$TEST_STATE/volume-reads\" ;;\n"
            "  get-sink-mute) echo 'Mute: no' ;;\n"
            "  subscribe)\n"
            "    for i in 1 2 3 4 5 6 7 8 9 10; do\n"
            "      echo \"Event 'change' on sink #0\"\n"
            "    done ;;\n"
            "esac\n")
        pactl.chmod(0o755)
        env = dict(self.env, XDG_CONFIG_HOME=str(self.state / 'config'))
        result = subprocess.run([str(BIN / 'spaced-audio-restore')], env=env,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            (self.state / 'config' / 'spaced' / 'audio-state').read_text().split(),
            ['50', 'no', 'spaced-test-sink'])
        # One read for the initial state and one for the settled burst, rather
        # than one per event.
        self.assertEqual(len((self.state / 'volume-reads').read_text().split()), 3)

    def test_display_power_policy_is_skipped_without_the_mate_schema(self):
        (self.state / 'xrandr').write_text('DP-0 connected primary 1920x1080+0+0\n')
        self.command('xrandr', 'if [ "$*" = --prop ]; then cat "$TEST_STATE/xrandr"; else exit 0; fi')
        self.command('xset', 'printf "%s\\n" "$*" >> "$TEST_STATE/power-writes"')
        self.command('gsettings', 'case "$1" in list-schemas) echo org.example.other ;; esac')
        self.assertEqual(self.run_helper('spaced-display-repair').returncode, 0)
        self.assertFalse((self.state / 'power-writes').exists())


class DesktopIconTests(unittest.TestCase):
    """Issue #184: desktop icons saved against a monitor that no longer exists."""

    LAYOUT = ('Screen 0: minimum 8 x 8, current 5760 x 1080, maximum 16384 x 16384\n'
              'DP-0 connected primary 1920x1080+0+0 (normal left inverted right)\n'
              '   1920x1080 60.00*+\n'
              'DP-1 connected 1920x1080+1920+0 (normal left inverted right)\n'
              '   1920x1080 60.00*+\n'
              'HDMI-1 connected (normal left inverted right)\n'
              'HDMI-2 disconnected (normal left inverted right)\n')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)
        self.fakebin = self.state / 'bin'
        self.fakebin.mkdir()
        self.config = self.state / '.config'
        (self.config / 'caja').mkdir(parents=True)
        self.desktop = self.state / 'Desktop'
        self.desktop.mkdir()
        self.env = dict(os.environ, HOME=str(self.state), DISPLAY=':spaced-test',
                        XDG_CONFIG_HOME=str(self.config), XDG_DESKTOP_DIR=str(self.desktop),
                        TEST_STATE=str(self.state),
                        PATH=str(self.fakebin) + os.pathsep + os.environ['PATH'])
        self.command('xrandr', 'cat "$TEST_STATE/xrandr"')
        (self.state / 'xrandr').write_text(self.LAYOUT)

    def command(self, name, body):
        path = self.fakebin / name
        path.write_text('#!/bin/bash\n' + body + '\n')
        path.chmod(0o755)

    def run_repair(self):
        return subprocess.run([str(BIN / 'spaced-desktop-icon-repair')], env=self.env,
                              capture_output=True, text=True, timeout=20)

    def metadata(self, text):
        path = self.config / 'caja' / 'desktop-metadata'
        path.write_text(text)
        return path

    def test_login_repair_finishes_before_caja_desktop_phase(self):
        pre_caja = (ROOT / 'overlays/etc/xdg/autostart/'
                    'spaced-desktop-icon-repair-before-caja.desktop').read_text()
        watcher = (ROOT / 'overlays/etc/xdg/autostart/'
                   'spaced-desktop-icon-repair.desktop').read_text()
        self.assertIn('Exec=/usr/local/bin/spaced-desktop-icon-repair\n', pre_caja)
        self.assertNotIn('--watch', pre_caja)
        self.assertIn('X-MATE-Autostart-Phase=Panel', pre_caja)
        self.assertIn('Exec=/usr/local/bin/spaced-desktop-icon-repair --watch', watcher)
        self.assertIn('X-MATE-Autostart-Phase=Applications', watcher)

    def test_offscreen_volume_positions_are_cleared_and_others_kept(self):
        path = self.metadata(
            '[smb:__nas__public]\ncaja-icon-position=7400,2600\n'
            '[smb:__nas__media]\ncaja-icon-position=64,120\n'
            '[trash]\ncaja-icon-position=3000,900\n')
        result = self.run_repair()
        self.assertEqual(result.returncode, 0, result.stderr)
        parser = configparser.ConfigParser(interpolation=None, strict=False)
        parser.optionxform = str
        parser.read_string(path.read_text())
        self.assertNotIn('caja-icon-position', parser['smb:__nas__public'])
        self.assertEqual(parser['smb:__nas__media']['caja-icon-position'], '64,120')
        self.assertEqual(parser['trash']['caja-icon-position'], '3000,900')
        self.assertIn('smb:__nas__public', result.stdout)

    def test_a_desktop_that_is_entirely_on_screen_is_left_alone(self):
        path = self.metadata('[smb:__nas__public]\ncaja-icon-position=64,120\n')
        before = (path.read_bytes(), path.stat().st_mtime_ns)
        result = self.run_repair()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), before)
        self.assertEqual(result.stdout, '')

    def test_unreadable_layout_makes_the_repair_do_nothing(self):
        self.command('xrandr', 'exit 1')
        path = self.metadata('[smb:__nas__public]\ncaja-icon-position=7400,2600\n')
        before = path.read_bytes()
        self.assertEqual(self.run_repair().returncode, 0)
        self.assertEqual(path.read_bytes(), before)

    def test_stranded_file_icon_positions_are_unset_through_gio(self):
        (self.desktop / 'Public on nas').write_text('')
        (self.desktop / 'Notes.txt').write_text('')
        self.command('gio',
                     'if [ "$1" = info ]; then\n'
                     '  case "$4" in\n'
                     '    *"Public on nas") echo "  metadata::caja-icon-position: 9000,4000" ;;\n'
                     '    *) echo "  metadata::caja-icon-position: 100,200" ;;\n'
                     '  esac\n'
                     'else\n'
                     '  printf "%s\\n" "$*" >> "$TEST_STATE/gio-writes"\n'
                     'fi')
        result = self.run_repair()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.state / 'gio-writes').read_text().splitlines(),
                         [f'set -t unset {self.desktop}/Public on nas '
                          'metadata::caja-icon-position'])

    def test_custom_xdg_desktop_directory_is_used_without_environment_override(self):
        custom_desktop = self.state / 'Arbeitsfläche'
        custom_desktop.mkdir()
        (self.config / 'user-dirs.dirs').write_text(
            'XDG_DESKTOP_DIR="$HOME/Arbeitsfläche"\n')
        (custom_desktop / 'Public on nas').write_text('')
        environment = dict(self.env)
        environment.pop('XDG_DESKTOP_DIR')
        self.command('gio',
                     'if [ "$1" = info ]; then\n'
                     '  echo "  metadata::caja-icon-position: 9000,4000"\n'
                     '  else printf "%s\\n" "$*" >> "$TEST_STATE/gio-writes"\n'
                     'fi')
        result = subprocess.run([str(BIN / 'spaced-desktop-icon-repair')], env=environment,
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            (self.state / 'gio-writes').read_text().splitlines(),
            [f'set -t unset {custom_desktop}/Public on nas metadata::caja-icon-position'])


class ThemeSwitchTests(unittest.TestCase):
    """Issue #181: rapid theme switching pegged the CPU and crashed the desktop."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)
        self.fakebin = self.state / 'bin'
        self.fakebin.mkdir()

    def command(self, name, body):
        path = self.fakebin / name
        path.write_text('#!/bin/bash\n' + body + '\n')
        path.chmod(0o755)

    def test_a_burst_of_theme_changes_applies_only_the_settled_choice(self):
        script = BIN / 'spaced-theme-monitor'
        source = script.read_text()
        start = source.index('SETTLE_SECONDS=')
        harness = self.state / 'loop.sh'
        harness.write_text(
            '#!/bin/bash\nset -u\n'
            'applied=()\n'
            'get_gtk() { cat "$TEST_STATE/current"; }\n'
            'apply_for_gtk() { applied+=("$1"); }\n'
            'save_desktop_state() { :; }\n'
            'LAST=Spaced-Linux-Dark\n'
            + source[start:source.index("done < <(gsettings monitor", start)]
            + 'done < <(\n'
            '  for theme in A B C D E F G H; do\n'
            '    printf "%s" "$theme" > "$TEST_STATE/current"; echo change; sleep 0.02\n'
            '  done\n'
            '  sleep 0.5\n'
            '  printf Z > "$TEST_STATE/current"; echo change\n'
            ')\n'
            'printf "%s\\n" "${applied[@]}"\n')
        harness.chmod(0o755)
        env = dict(os.environ, TEST_STATE=str(self.state),
                   SPACED_THEME_SETTLE_SECONDS='0.25')
        (self.state / 'current').write_text('Spaced-Linux-Dark')
        result = subprocess.run(['bash', str(harness)], env=env, capture_output=True,
                                text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        # Eight rapid clicks collapse into one switch; the later, separate
        # choice still gets applied.
        self.assertEqual(result.stdout.split(), ['H', 'Z'])


if __name__ == '__main__':
    unittest.main()
