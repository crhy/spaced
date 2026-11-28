"""crhy/spacedupdate#17: the shipped updater repairs an old install's GRUB theme."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'overlays/usr/lib/spaced-linux/spaced-update-helper'
POLICY = ROOT / 'overlays/usr/lib/spaced-linux/spaced-policy-rc.d'
CANONICAL = 'GRUB_THEME="/boot/grub/themes/spaced/theme.txt"'


class GrubThemeRepairTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.grub_root = base / 'root'
        self.etc_default = self.grub_root / 'etc/default'
        self.grub_d = self.etc_default / 'grub.d'
        self.theme_dir = self.grub_root / 'boot/grub/themes/spaced'
        self.state = base / 'state'
        self.fakebin = base / 'bin'
        for path in (self.etc_default, self.grub_d, self.theme_dir,
                     self.state, self.fakebin):
            path.mkdir(parents=True)
        # The packaged self-contained theme staged by spaced-themes 9.26+.
        (self.theme_dir / 'theme.txt').write_text(
            'desktop-image: "SimpleBackb.png"\n')
        (self.theme_dir / 'SimpleBackb.png').write_bytes(b'\x89PNG\n')
        (self.theme_dir / 'spaced-icon-fancy.png').write_bytes(b'\x89PNG\n')
        self.guard = self.state / 'spaced-update-apt-guard'
        self.guard.write_text('#!/bin/bash\nexit 0\n')
        self.guard.chmod(0o755)
        self.command('apt-get', 'exit 0')
        self.command('dpkg', 'exit 0')
        self.command('apt-mark', 'exit 0')
        self.command('update-initramfs', 'exit 0')
        self.command('findmnt', 'printf "%s\\n" "$ROOT_FSTYPE"')
        self.command('update-grub',
                     'printf "update-grub\\n" >> "$TEST_STATE/commands"')
        self.command('flatpak', 'exit 0')
        self.env = dict(os.environ,
                        PATH=str(self.fakebin) + os.pathsep + os.environ['PATH'],
                        TEST_STATE=str(self.state), ROOT_FSTYPE='ext4',
                        SPACED_UPDATE_TEST='1',
                        SPACED_UPDATE_TEST_GRUB_ROOT=str(self.grub_root),
                        SPACED_UPDATE_TEST_SESSION_PAYLOAD=str(POLICY),
                        SPACED_UPDATE_TEST_SESSION_POLICY=str(base / 'policy-rc.d'),
                        SPACED_UPDATE_TEST_GUARD=str(self.guard))

    def command(self, name, body):
        path = self.fakebin / name
        path.write_text('#!/bin/bash\n' + body + '\n')
        path.chmod(0o755)

    def write_grub(self, text):
        grub = self.etc_default / 'grub'
        grub.write_text(text)
        return grub

    def run_helper(self):
        return subprocess.run(['bash', str(HELPER), 'all'], env=self.env,
                              capture_output=True, text=True, timeout=60)

    def update_grub_runs(self):
        commands = self.state / 'commands'
        if not commands.exists():
            return 0
        return sum(1 for line in commands.read_text().splitlines()
                   if line == 'update-grub')

    def test_broken_8266_background_is_repointed_at_the_packaged_theme(self):
        grub = self.write_grub(
            'GRUB_DEFAULT=0\n'
            + CANONICAL + '\n'
            'GRUB_BACKGROUND="/usr/share/backgrounds/spaced/SimpleBackb.png"\n')
        result = self.run_helper()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('crhy/spacedupdate#17', result.stdout)
        text = grub.read_text()
        self.assertIn(CANONICAL, text)
        self.assertNotIn('GRUB_BACKGROUND', text)
        self.assertEqual(self.update_grub_runs(), 1)
        # The packaged theme files were not rewritten.
        self.assertEqual((self.theme_dir / 'theme.txt').read_text(),
                         'desktop-image: "SimpleBackb.png"\n')

    def test_broken_8266_theme_path_is_repointed_at_the_packaged_theme(self):
        grub = self.write_grub('GRUB_DEFAULT=0\n'
                               'GRUB_THEME="/usr/share/spaced-themes/grub/theme.txt"\n')
        result = self.run_helper()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('crhy/spacedupdate#17', result.stdout)
        self.assertIn(CANONICAL, grub.read_text())
        self.assertNotIn('/usr/share/spaced-themes', grub.read_text())
        self.assertEqual(self.update_grub_runs(), 1)

    def test_grub_d_snippet_is_repaired_and_main_grub_untouched(self):
        grub = self.write_grub(
            'GRUB_DEFAULT=0\n'
            '#GRUB_THEME="/boot/grub/themes/spaced/theme.txt"\n')
        snippet = self.grub_d / '40spaced.cfg'
        snippet.write_text(
            'GRUB_BACKGROUND="/usr/share/backgrounds/spaced/SimpleBackb.png"\n')
        result = self.run_helper()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('crhy/spacedupdate#17', result.stdout)
        self.assertIn(CANONICAL, snippet.read_text())
        # A pre-8.26.6 commented-out line is never enabled by the repair.
        self.assertEqual(grub.read_text(),
                         'GRUB_DEFAULT=0\n'
                         '#GRUB_THEME="/boot/grub/themes/spaced/theme.txt"\n')
        self.assertEqual(self.update_grub_runs(), 1)

    def test_already_good_theme_is_unchanged(self):
        grub = self.write_grub('GRUB_DEFAULT=0\n' + CANONICAL + '\n')
        original = grub.read_text()
        result = self.run_helper()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('crhy/spacedupdate#17', result.stdout)
        self.assertEqual(grub.read_text(), original)
        self.assertEqual(self.update_grub_runs(), 1)

    def test_other_theme_is_never_touched_even_if_missing(self):
        grub = self.write_grub(
            'GRUB_THEME="/boot/grub/themes/personal/personal.theme"\n'
            'GRUB_BACKGROUND="/usr/share/backgrounds/wallpaper.png"\n')
        original = grub.read_text()
        result = self.run_helper()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('crhy/spacedupdate#17', result.stdout)
        self.assertEqual(grub.read_text(), original)

    def test_missing_grub_configuration_skips_the_repair(self):
        result = self.run_helper()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('crhy/spacedupdate#17', result.stdout)
        self.assertFalse((self.etc_default / 'grub').exists())

    def test_repair_waits_while_the_packaged_theme_is_absent(self):
        for name in ('theme.txt', 'SimpleBackb.png', 'spaced-icon-fancy.png'):
            (self.theme_dir / name).unlink()
        grub = self.write_grub(
            'GRUB_BACKGROUND="/usr/share/backgrounds/spaced/SimpleBackb.png"\n')
        original = grub.read_text()
        result = self.run_helper()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('packaged Spaced GRUB theme is not installed', result.stdout)
        self.assertEqual(grub.read_text(), original)


if __name__ == '__main__':
    unittest.main()
