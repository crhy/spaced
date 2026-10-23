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
