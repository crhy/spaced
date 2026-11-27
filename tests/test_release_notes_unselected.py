"""The "What's new" notes dialog opens with its notes unselected
(crhy/spacedupdate#20).

GTK3 selects the whole text of a selectable GtkLabel once it receives a
window's initial keyboard focus, and the notes window's first focusable
widget is its selectable notes label, so the notes used to open fully
highlighted.  This check builds the real notes dialog headless, one
subprocess under xvfb-run like the contrast test, and asserts that after
show the window's focus is the Close button and the notes label's AtkText
reports no selection.
"""
from pathlib import Path
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True

APP = ROOT / 'overlays/usr/lib/spaced-linux/spaced-update.py'

NOTES = ('One: the notes open unselected.\n'
         'Two: the Close button takes the initial focus.')

CHECK_SOURCE = '''"""Open the real What's new dialog headless and report focus/selection."""
import os
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
import importlib.util

spec = importlib.util.spec_from_file_location('spaced_update_app',
                                              os.environ['SPACED_UPDATE_APP'])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

app = module.App()
app.show_all()
app.os_tab.latest_release = '9.26.1'
app.os_tab.release_notes = os.environ['SPACED_TEST_NOTES']
dialog = app.os_tab.build_notes_dialog()
dialog.show_all()
while Gtk.events_pending():
    Gtk.main_iteration()


def walk(widget):
    yield widget
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            yield from walk(child)


close = [w for w in walk(dialog) if isinstance(w, Gtk.Button)]
assert len(close) == 1, 'expected one Close button, found %d' % len(close)
notes = [w for w in walk(dialog)
         if isinstance(w, Gtk.Label) and w.get_selectable()]
assert len(notes) == 1, 'expected one selectable notes label, found %d' % len(notes)
focus = dialog.get_focus()
n_selections = notes[0].get_accessible().get_n_selections()
print('focus_is_close=%s selectable=%s has_text=%s selections=%d'
      % (focus is close[0], notes[0].get_selectable(),
         bool(notes[0].get_text().strip()), n_selections))
'''


@unittest.skipIf(shutil.which('xvfb-run') is None, 'needs xvfb-run')
@unittest.skipIf(not APP.is_file(), 'needs spaced-update.py')
class ReleaseNotesUnselectedTests(unittest.TestCase):
    def test_notes_window_opens_unselected_with_focus_on_close(self):
        workdir = Path(tempfile.mkdtemp(prefix='notes-focus-'))
        self.addCleanup(shutil.rmtree, workdir, True)
        script = workdir / 'check_notes_focus.py'
        script.write_text(CHECK_SOURCE)
        env = dict(os.environ,
                   SPACED_UPDATE_APP=str(APP),
                   SPACED_UPDATE_NO_AUTOCHECK='1',
                   PYTHONDONTWRITEBYTECODE='1',
                   SPACED_TEST_NOTES=NOTES)
        result = subprocess.run(['xvfb-run', '-a', 'python3', str(script)],
                                env=env, timeout=60, capture_output=True)
        self.assertEqual(result.returncode, 0,
                         'opening the notes dialog failed: %s'
                         % result.stderr.decode())
        stdout = result.stdout.decode()
        self.assertRegex(
            stdout, r'focus_is_close=True selectable=True has_text=True '
                    r'selections=0\b',
            'the notes must open unselected with focus on the Close button, '
            'got: %s' % stdout)


if __name__ == '__main__':
    unittest.main()
