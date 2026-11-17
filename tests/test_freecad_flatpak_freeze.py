"""The FreeCAD flatpak gray-freeze record, its workaround, and the override
11.26.3 ships for it (#425, found in f078).

FreeCAD 1.1.4's flatpak deadlocks in its own notification area, so the real fix
belongs upstream in FreeCAD. What Spaced ships is the measured workaround as a
system flatpak override for that one application id. These tests pin the record,
the shipped file, the fact that the build installs it, the upgrade path that
carries it, and the flatpak override layering that limits where a system override
reaches and keeps a user's own override intact.
"""
from pathlib import Path
import configparser
import re
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
FIXES = REPO / 'docs' / 'FIXES.md'
UPSTREAM_DOC = REPO / 'docs' / 'upstream' / 'freecad-notificationarea-deadlock.md'
OVERRIDE = REPO / 'overlays/var/lib/flatpak/overrides/org.freecad.FreeCAD'
POSTINST = (REPO / 'packages/spaced-meta/DEBIAN/postinst').read_text()
MAKEFILE = (REPO / 'Makefile').read_text()
EXCLUDES = (REPO / 'live-build/config/rootfs/excludes').read_text()
APP_ID = 'org.freecad.FreeCAD'
KEY = 'QT_LOGGING_RULES'
RULE = 'qt.accessibility.atspi=false'
CONTENTS = f'[Environment]\n{KEY}={RULE}\n'
IMAGE_PATH = '/var/lib/flatpak/overrides/org.freecad.FreeCAD'
COMMAND = 'flatpak run --env=QT_LOGGING_RULES=qt.accessibility.atspi=false org.freecad.FreeCAD'


def freeze_row() -> str:
    for line in FIXES.read_text(encoding='utf-8').splitlines():
        if line.startswith('| FreeCAD 1.1.4 flatpak'):
            return line
    raise AssertionError('docs/FIXES.md has no FreeCAD flatpak freeze row')


def layering_row() -> str:
    for line in FIXES.read_text(encoding='utf-8').splitlines():
        if line.startswith('| A system flatpak override'):
            return line
    raise AssertionError('docs/FIXES.md has no flatpak override layering row')


def upgrade_block() -> str:
    match = re.search(r'(?ms)^override=/var/lib/flatpak/overrides/org\.freecad\.FreeCAD'
                      r'.*?^fi$', POSTINST)
    assert match, 'spaced-meta postinst has no FreeCAD flatpak override block'
    return match.group(0)


def run_upgrade_block(root: Path, action: str = 'configure', preexisting=None):
    """Run only the override block of the postinst against a scratch root."""
    script = (upgrade_block()
              .replace('/var/lib/flatpak', str(root / 'var/lib/flatpak'))
              .replace('/var/lib/spaced-linux', str(root / 'var/lib/spaced-linux')))
    if preexisting is not None:
        override = root / 'var/lib/flatpak/overrides'
        override.mkdir(parents=True)
        (override / APP_ID).write_text(preexisting)
    subprocess.run(['sh', '-c', script, 'sh', action], check=True)


class FreecadFlatpakFreezeRecordTests(unittest.TestCase):
    def test_record_names_the_locking_pair_that_deadlocks(self):
        row = freeze_row()
        for token in ('mutexNotification', 'showInNotificationArea', 'pushNotification',
                      'Received text event for invalid interface', 'AT_SPI_BUS_ADDRESS'):
            self.assertIn(token, row)

    def test_record_names_the_measured_workaround_verbatim(self):
        self.assertIn(COMMAND, freeze_row())

    def test_workaround_is_a_well_formed_flatpak_invocation(self):
        parts = COMMAND.split()
        self.assertEqual(parts[:2], ['flatpak', 'run'])
        self.assertEqual(parts[-1], 'org.freecad.FreeCAD')
        self.assertTrue(parts[2].startswith('--env='))
        key, _, rule = parts[2][len('--env='):].partition('=')
        self.assertEqual(key, 'QT_LOGGING_RULES')
        self.assertEqual(rule, 'qt.accessibility.atspi=false')

    def test_record_keeps_the_fix_upstream_instead_of_in_an_overlay(self):
        row = freeze_row()
        self.assertIn('upstream', row)
        self.assertNotIn('overlays/etc/profile.d', row)

    def test_record_is_one_markdown_table_row(self):
        self.assertEqual(freeze_row().count('|'), 4)


class FreecadFlatpakOverrideFileTests(unittest.TestCase):
    def test_the_image_ships_a_system_flatpak_override(self):
        self.assertTrue(OVERRIDE.is_file())
        self.assertEqual(OVERRIDE.relative_to(REPO),
                         Path('overlays/var/lib/flatpak/overrides/org.freecad.FreeCAD'))

    def test_the_override_carries_exactly_that_key_and_value(self):
        self.assertEqual(OVERRIDE.read_text(encoding='utf-8'), CONTENTS)
        parser = configparser.RawConfigParser(strict=True, interpolation=None)
        parser.optionxform = str
        parser.read_string(OVERRIDE.read_text(encoding='utf-8'))
        self.assertEqual(parser.sections(), ['Environment'])
        self.assertEqual(parser.options('Environment'), [KEY])
        self.assertEqual(parser.get('Environment', KEY), RULE)

    def test_the_override_names_the_flatpak_app_id_in_the_system_layer(self):
        self.assertEqual(OVERRIDE.name, APP_ID)
        self.assertEqual(OVERRIDE.parent.name, 'overrides')
        self.assertEqual(Path(OVERRIDE.relative_to(REPO / 'overlays')).as_posix(),
                         IMAGE_PATH.lstrip('/'))

    def test_the_shipped_rule_is_the_measured_workaround(self):
        self.assertIn(f'{KEY}={RULE}', OVERRIDE.read_text(encoding='utf-8'))
        self.assertIn(f'--env={KEY}={RULE}', COMMAND)

    def test_the_build_installs_the_override_into_the_image_root(self):
        self.assertIn('cp -a overlays/. $(LB_DIR)/config/includes.chroot/', MAKEFILE)
        self.assertNotIn('var/lib', EXCLUDES)

    def test_the_override_is_readable_by_every_user_and_not_executable(self):
        # flatpak reads this file from a normal desktop account, so it must stay
        # world-readable and must never be executable.
        mode = OVERRIDE.stat().st_mode
        self.assertFalse(mode & 0o111)
        self.assertTrue(mode & 0o004)
        for directory in OVERRIDE.parents[:4]:
            self.assertTrue(directory.is_dir())
            self.assertTrue(directory.stat().st_mode & 0o004)

    def test_only_that_one_application_gets_the_rule(self):
        offenders = [path.relative_to(REPO) for path in (REPO / 'overlays').rglob('*')
                     if path.is_file() and KEY in path.read_text(encoding='utf-8', errors='ignore')]
        self.assertEqual(offenders, [OVERRIDE.relative_to(REPO)])


class FreecadFlatpakOverrideUpgradeTests(unittest.TestCase):
    def test_upgrade_writes_the_same_file_the_image_ships(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_upgrade_block(root)
            override = root / 'var/lib/flatpak/overrides' / APP_ID
            self.assertEqual(override.read_text(encoding='utf-8'),
                             OVERRIDE.read_text(encoding='utf-8'))
            self.assertEqual(override.stat().st_mode & 0o777, 0o644)
            self.assertTrue((root / 'var/lib/spaced-linux/freecad-flatpak-override-11.26.3').exists())

    def test_a_second_configuration_changes_nothing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_upgrade_block(root)
            override = root / 'var/lib/flatpak/overrides' / APP_ID
            first = override.read_text(encoding='utf-8')
            run_upgrade_block(root)
            self.assertEqual(override.read_text(encoding='utf-8'), first)

    def test_an_existing_system_override_is_never_replaced(self):
        admin = '[Context]\nshare=network;\n\n[Environment]\nMY_APP_VAR=keep-me\n'
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_upgrade_block(root, preexisting=admin)
            self.assertEqual((root / 'var/lib/flatpak/overrides' / APP_ID).read_text(), admin)
            # The migration is satisfied, so it must not repeat at every upgrade.
            self.assertTrue((root / 'var/lib/spaced-linux/freecad-flatpak-override-11.26.3').exists())

    def test_the_per_user_layer_is_never_written_from_root(self):
        block = upgrade_block()
        for forbidden in ('--user', '.local/share/flatpak', '.var/app', '$HOME', '~'):
            self.assertNotIn(forbidden, block)

    def test_a_triggered_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_upgrade_block(root, action='triggered')
            self.assertFalse((root / 'var/lib/flatpak').exists())
            self.assertFalse((root / 'var/lib/spaced-linux').exists())


class FreecadOverrideLayeringRecordTests(unittest.TestCase):
    """flatpak reads the system override layer only for apps installed in the
    system installation, and merges the per-user layer last."""

    def test_the_record_names_the_layer_that_limits_a_system_override(self):
        row = layering_row()
        for token in ('Only load system overrides for system installed apps',
                      'per-user', 'merged last', 'clobber'):
            self.assertIn(token, row)

    def test_the_record_is_one_markdown_table_row(self):
        self.assertEqual(layering_row().count('|'), 4)

    def test_the_shipped_override_row_points_at_the_implementation(self):
        for token in ('overlays/var/lib/flatpak/overrides/org.freecad.FreeCAD',
                      'packages/spaced-meta/DEBIAN/postinst',
                      'docs/upstream/freecad-notificationarea-deadlock.md'):
            self.assertIn(token, FIXES.read_text(encoding='utf-8'))


class FreecadUpstreamReportTests(unittest.TestCase):
    def test_the_upstream_report_travels_with_the_repo(self):
        self.assertTrue(UPSTREAM_DOC.is_file())
        text = UPSTREAM_DOC.read_text(encoding='utf-8')
        for token in ('NotificationArea', 'mutexNotification',
                      'Received text event for invalid interface',
                      'recursive_mutex', 'AT_SPI_BUS_ADDRESS', COMMAND):
            self.assertIn(token, text)

    def test_the_report_is_marked_as_not_filed_yet(self):
        self.assertIn('not filed', UPSTREAM_DOC.read_text(encoding='utf-8').lower())

    def test_the_freeze_record_links_the_upstream_report(self):
        self.assertIn('docs/upstream/freecad-notificationarea-deadlock.md', freeze_row())


if __name__ == '__main__':
    unittest.main()
