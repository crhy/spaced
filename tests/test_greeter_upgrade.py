"""Run the conservative installed-system avatar migration in scratch files."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
POSTINST = (ROOT / 'packages/spaced-mate-default-settings/DEBIAN/postinst').read_text()
BLOCK = re.search(r'(?ms)^greeter_conf=.*?^fi$', POSTINST).group(0)
OLD = '/usr/share/icons/hicolor/256x256/apps/spaced-linux.png'
NEW = '/usr/share/pixmaps/spaced-medallion.png'


class GreeterUpgradeTests(unittest.TestCase):
    def migrate(self, content):
        with tempfile.TemporaryDirectory() as tmp:
            conf = Path(tmp) / 'greeter.conf'
            if content is not None:
                conf.write_text(content)
            script = BLOCK.replace('/etc/lightdm/lightdm-gtk-greeter.conf', str(conf))
            subprocess.run(['sh', '-ec', script], check=True)
            return conf.read_text() if conf.exists() else None

    def test_old_default_upgrades_once(self):
        before = f'[greeter]\ndefault-user-image={OLD}\nbackground=#000000\n'
        after = self.migrate(before)
        self.assertEqual(after, before.replace(OLD, NEW))
        self.assertEqual(self.migrate(after), after)

    def test_custom_and_commented_settings_are_preserved(self):
        for value in ['/opt/custom.png', OLD + '.backup', OLD.replace('.png', '-png')]:
            conf = f'[greeter]\n#default-user-image={OLD}\ndefault-user-image={value}\n'
            self.assertEqual(self.migrate(conf), conf)

    def test_absent_config_is_not_created(self):
        self.assertIsNone(self.migrate(None))
