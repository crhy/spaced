"""The measured FreeCAD flatpak gray-freeze record and its workaround (#f078).

FreeCAD 1.1.4's flatpak deadlocks in its own notification area. Spaced ships no
fix for it, so the resolution record must keep naming the real owner and the
exact command that was measured to work; this test pins both.
"""
from pathlib import Path
import re
import unittest

REPO = Path(__file__).resolve().parents[1]
FIXES = REPO / 'docs' / 'FIXES.md'
COMMAND = 'flatpak run --env=QT_LOGGING_RULES=qt.accessibility.atspi=false org.freecad.FreeCAD'


def freeze_row() -> str:
    for line in FIXES.read_text(encoding='utf-8').splitlines():
        if line.startswith('| FreeCAD 1.1.4 flatpak'):
            return line
    raise AssertionError('docs/FIXES.md has no FreeCAD flatpak freeze row')


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


if __name__ == '__main__':
    unittest.main()
