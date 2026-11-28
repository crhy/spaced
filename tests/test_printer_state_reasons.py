"""Issue #440: a successful print job must not be shown as a printer error.

Spaced ships overlays/usr/share/system-config-printer/statereason.py over the
Debian file; it classifies printer-state-reasons by the IPP suffix rules:
'-error' = error, '-warning' = warning, '-report' or unsuffixed = not an
error, and the reasons a printing queue reports ("cups-waiting-for-job-completed",
"processing") say "Printing…" instead of "Printer error".
"""
from pathlib import Path
import importlib.util
import sys
import types
import unittest


ROOT = Path(__file__).resolve().parents[1]
STATEREASON = (ROOT / 'overlays/usr/share/system-config-printer'
                / 'statereason.py')


def load_statereason():
    """Import the shipped copy without needing python3-cups or the
    system-config-printer config module on sys.path."""
    saved = {name: sys.modules.get(name)
             for name in ('cups', 'config')}
    cups_stub = types.ModuleType('cups')
    config_stub = types.ModuleType('config')
    config_stub.PACKAGE = 'system-config-printer'
    config_stub.localedir = '/nonexistent'
    sys.modules['cups'] = cups_stub
    sys.modules['config'] = config_stub
    try:
        spec = importlib.util.spec_from_file_location('spaced_statereason',
                                                      str(STATEREASON))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for name, old in saved.items():
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old


class PrinterStateReasonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.statereason = load_statereason()
        cls.StateReason = cls.statereason.StateReason

    def reason(self, reason):
        return self.StateReason('Spaced_Network_Printer', reason)

    def test_shipped_override_is_a_plain_file(self):
        self.assertTrue(STATEREASON.is_file())
        self.assertFalse(STATEREASON.stat().st_mode & 0o111)

    def test_printing_reasons_are_not_errors_and_say_printing(self):
        for reason in ('cups-waiting-for-job-completed', 'processing'):
            with self.subTest(reason=reason):
                state = self.reason(reason)
                self.assertNotEqual(state.get_level(), self.StateReason.ERROR)
                title, text = state.get_description()
                self.assertEqual(title, 'Printing…')
                self.assertIn('printing', text.lower())

    def test_report_suffix_and_unsuffixed_reasons_are_not_errors(self):
        for reason in ('ipp-republishing-report',
                       'cups-waiting-for-job-completed',
                       'media-low',
                       'connecting-to-device',
                       'cups-ipp-missing-job-id'):
            with self.subTest(reason=reason):
                state = self.reason(reason)
                self.assertEqual(state.get_level(), self.StateReason.REPORT)
                title, _ = state.get_description()
                self.assertNotEqual(title, 'Printer error')

    def test_warning_suffix_reasons_are_warnings_not_errors(self):
        for reason in ('marker-supply-warning', 'media-needed-warning'):
            with self.subTest(reason=reason):
                state = self.reason(reason)
                self.assertEqual(state.get_level(), self.StateReason.WARNING)
                title, _ = state.get_description()
                self.assertNotEqual(title, 'Printer error')

    def test_error_suffix_and_stopped_are_the_only_real_errors(self):
        for reason in ('media-error', 'display-error', 'server-error',
                       'stopped'):
            with self.subTest(reason=reason):
                self.assertEqual(self.reason(reason).get_level(),
                                 self.StateReason.ERROR)

    def test_real_error_still_shows_the_error_wording(self):
        title, text = self.reason('media-error').get_description()
        self.assertEqual(title, 'Printer error')
        self.assertIn('Spaced_Network_Printer', text)

    def test_upstream_message_table_survives_the_override(self):
        title, text = self.reason('cover-open').get_description()
        self.assertEqual(title, 'Cover open')
        self.assertIn('cover is open', text)

    def test_reason_levels_sort_for_the_worst_reason_pick(self):
        report = self.reason('media-low')
        warning = self.reason('media-needed-warning')
        error = self.reason('media-error')
        self.assertLess(report, warning)
        self.assertLess(warning, error)
        self.assertGreater(error, report)


if __name__ == '__main__':
    unittest.main()
