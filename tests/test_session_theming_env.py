"""The X session must load the toolkit theming exports (#339)."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
XSESSION = REPO / 'overlays/etc/X11/Xsession.d/40spaced-application-theming'
PROFILE = REPO / 'overlays/etc/profile.d/spaced-application-theming.sh'
PROFILE_PATH = '/etc/profile.d/spaced-application-theming.sh'
PROBE = ('. "{xsession}"; printf "%s|%s|%s" "$QT_QPA_PLATFORMTHEME" '
         '"$QT_STYLE_OVERRIDE" "$SAL_USE_VCLPLUGIN"')


class SessionThemingEnvTests(unittest.TestCase):
    def test_palette_directory_exists_before_desktop_apps_start(self):
        for custom_config in (False, True):
            with self.subTest(custom_config=custom_config), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                env = {'PATH': os.environ['PATH'], 'HOME': str(root)}
                config = root / ('custom-config' if custom_config else '.config')
                if custom_config:
                    env['XDG_CONFIG_HOME'] = str(config)
                script = XSESSION.read_text().replace(PROFILE_PATH, str(root / 'absent-profile'))
                subprocess.run(['sh', '-c', script], env=env, check=True)
                self.assertTrue((config / 'spaced').is_dir())
                self.assertEqual((config / 'spaced').stat().st_mode & 0o777, 0o700)
                marker = config / 'spaced/libadwaita.css'
                marker.write_text('preserve existing palette')
                subprocess.run(['sh', '-c', script], env=env, check=True)
                self.assertEqual(marker.read_text(), 'preserve existing palette')

    def test_xsession_loads_theming_exports(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = root / 'spaced-application-theming.sh'
            profile.write_text(PROFILE.read_text(encoding='utf-8'))
            xsession = root / '40spaced-application-theming'
            xsession.write_text(XSESSION.read_text(encoding='utf-8').replace(PROFILE_PATH, str(profile)))
            result = subprocess.run(['sh', '-c', PROBE.format(xsession=xsession)],
                                    env={'PATH': os.environ['PATH']}, capture_output=True, text=True, check=True)
            self.assertEqual(result.stdout, 'gtk3|Fusion|gtk3')

    def test_xsession_survives_missing_profile_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            xsession = root / '40spaced-application-theming'
            xsession.write_text(XSESSION.read_text(encoding='utf-8').replace(
                PROFILE_PATH, str(root / 'absent-spaced-application-theming.sh')))
            result = subprocess.run(['sh', '-c', PROBE.format(xsession=xsession)],
                                    env={'PATH': os.environ['PATH']}, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, '||')


if __name__ == '__main__':
    unittest.main()
