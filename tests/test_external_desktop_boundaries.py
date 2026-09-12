"""Offline Caja metadata and GIMP launch boundaries, not GUI acceptance tests."""

import configparser
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / 'overlays/usr/local/bin'
REPAIR = runpy.run_path(str(BIN / 'spaced-desktop-icon-repair'))


class OfflineCajaMetadataTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'desktop-metadata'
        self.rectangles = [(0, 0, 1920, 1080), (3840, 0, 1920, 1080)]

    def repair(self):
        return REPAIR['repair_desktop_metadata'](self.path, self.rectangles)

    def test_only_unreachable_position_is_removed(self):
        self.path.write_text(
            '[smb:__nas__Données%20partagées]\n'
            'caja-icon-position=7400,2600\n'
            'caja-icon-scale=1.25\n'
            'icon-position-timestamp=123456\n'
            '[trash]\ncaja-icon-position=4000,200\n'
            'custom-key=Keep This Value\n', encoding='utf-8')
        self.assertEqual(self.repair(), ['smb:__nas__Données%20partagées'])
        metadata = configparser.ConfigParser(interpolation=None)
        metadata.read(self.path, encoding='utf-8')
        self.assertEqual(dict(metadata['smb:__nas__Données%20partagées']), {
            'caja-icon-scale': '1.25', 'icon-position-timestamp': '123456'})
        self.assertEqual(dict(metadata['trash']), {
            'caja-icon-position': '4000,200', 'custom-key': 'Keep This Value'})

    def test_gap_between_active_monitors_is_not_visible_desktop(self):
        self.path.write_text(
            '[gap]\ncaja-icon-position=3000,200\n'
            '[second-monitor]\ncaja-icon-position=4000,200\n')
        self.assertEqual(self.repair(), ['gap'])

    def test_second_offline_repair_does_not_rewrite_metadata(self):
        self.path.write_text('[share]\ncaja-icon-position=9000,4000\n')
        self.assertEqual(self.repair(), ['share'])
        before = (self.path.read_bytes(), self.path.stat().st_mtime_ns)
        self.assertEqual(self.repair(), [])
        self.assertEqual((self.path.read_bytes(), self.path.stat().st_mtime_ns), before)

    def test_invalid_metadata_is_preserved_byte_for_byte(self):
        self.path.write_bytes(b'not an ini file\ncaja-icon-position=9000,4000\n')
        before = self.path.read_bytes()
        self.assertEqual(self.repair(), [])
        self.assertEqual(self.path.read_bytes(), before)

    def test_unknown_position_format_is_not_discarded(self):
        self.path.write_text('[share]\ncaja-icon-position=unknown\n')
        before = self.path.read_bytes()
        self.assertEqual(self.repair(), [])
        self.assertEqual(self.path.read_bytes(), before)

    def test_missing_metadata_is_not_created(self):
        self.assertEqual(self.repair(), [])
        self.assertFalse(self.path.exists())


class GimpFlatpakLaunchTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.state = Path(temporary.name)
        self.log = self.state / 'arguments.json'
        real_flatpak = self.state / 'flatpak-real'
        real_flatpak.write_text(
            f'#!{sys.executable}\n'
            'import json, os, sys\n'
            'from pathlib import Path\n'
            'Path(os.environ["TEST_LOG"]).write_text(json.dumps({\n'
            '    "args": sys.argv[1:],\n'
            '    "environment": {name: os.environ.get(name) for name in\n'
            '        ("GTK_THEME", "GSK_RENDERER", "GDK_BACKEND")}\n'
            '}))\n'
            'print("application stdout")\n'
            'print("application stderr", file=sys.stderr)\n'
            'sys.exit(int(os.environ.get("TEST_EXIT", "0")))\n')
        real_flatpak.chmod(0o755)
        self.environment = dict(os.environ, HOME=str(self.state),
                                SPACED_FLATPAK_REAL=str(real_flatpak),
                                TEST_LOG=str(self.log))
        for name in ('GTK_THEME', 'GSK_RENDERER', 'GDK_BACKEND'):
            self.environment.pop(name, None)

    def launch(self, arguments):
        return subprocess.run(['bash', str(BIN / 'flatpak'), *arguments],
                              env=self.environment, capture_output=True,
                              text=True, timeout=10)

    def test_gimp_diagnostic_arguments_and_exit_status_pass_through(self):
        arguments = ['run', 'org.gimp.GIMP', '--new-instance', '--verbose',
                     '--stack-trace-mode=always', '/tmp/image with spaces.png']
        for status in (0, 139):
            with self.subTest(status=status):
                self.environment['TEST_EXIT'] = str(status)
                result = self.launch(arguments)
                self.assertEqual(result.returncode, status, result.stderr)
                self.assertEqual(result.stdout, 'application stdout\n')
                self.assertEqual(result.stderr, 'application stderr\n')
                recorded = json.loads(self.log.read_text())
                self.assertEqual(recorded['args'], arguments)
                self.assertEqual(recorded['environment'], {
                    'GTK_THEME': None, 'GSK_RENDERER': None, 'GDK_BACKEND': None})

    def test_gimp_launch_preserves_explicit_user_theme_and_backend(self):
        self.environment.update(GTK_THEME='Adwaita', GDK_BACKEND='x11')
        arguments = ['run', '--env=GTK_THEME=Adwaita', 'org.gimp.GIMP']
        result = self.launch(arguments)
        self.assertEqual(result.returncode, 0, result.stderr)
        recorded = json.loads(self.log.read_text())
        self.assertEqual(recorded['args'], arguments)
        self.assertEqual(recorded['environment'], {
            'GTK_THEME': 'Adwaita', 'GSK_RENDERER': None, 'GDK_BACKEND': 'x11'})


if __name__ == '__main__':
    unittest.main()
