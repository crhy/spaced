#!/usr/bin/env python3
"""Issue #439: an Intel-only PC (one UHD 630 at 0000:00:02.0) must still have a
GPU Manager where every tab and every button visibly does something: a page
changes, a dialog opens, or a plain-words message explains why the action is
not available on this PC. This probe drives the REAL app over the fake
Intel-only machine under Xvfb.

Root actions stay fake: pkexec, the privileged helpers and the installer are
replaced by recorders, so nothing privileged ever runs here. The help links
(GtkLinkButton) are only counted, never activated: they would open a browser.

Prints one PROBE line per check and PROBE_ALL_OK when all pass; exit 0 only
then. tests/test_gpu_manager.py runs it under xvfb-run."""
import argparse
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / 'overlays/usr/lib/spaced-linux'
sys.path.insert(0, str(LIB))

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gtk

spec = importlib.util.spec_from_file_location('gpu_manager_ui',
                                              str(LIB / 'spaced-gpu-manager.py'))
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)

FAILED = []


def check(name, condition, detail=''):
    if condition:
        print(f'PROBE ok {name}', flush=True)
    else:
        FAILED.append(name)
        print(f'PROBE fail {name} :: {detail}', flush=True)


class Fake:
    """What the app was asked to run, instead of running it."""
    dialogs = []          # label texts of every dialog that opened
    popens = []           # display-settings / installer launches
    privileged = []       # pkexec / helper invocations (never executed)
    response = 'cancel'   # next dialog response
    pick = None           # next dialog radio to activate before OK


def fake_run(args, *a, **k):
    argv = list(args) if isinstance(args, (list, tuple)) else [args]
    Fake.privileged.append(argv)

    class Result:
        returncode = 0
        stdout = 'fake helper output: ' + ' '.join(argv)
        stderr = ''
    return Result()


def fake_popen(argv, *a, **k):
    Fake.popens.append(list(argv))

    class Process:
        def poll(self):
            return 0
    return Process()


def labels_of(widget, found=None):
    found = [] if found is None else found
    if isinstance(widget, Gtk.Label) and widget.get_text():
        found.append(widget.get_text())
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            labels_of(child, found)
    return found


def fake_dialog_run(self, *args):
    texts = labels_of(self)
    Fake.dialogs.append(texts)
    if Fake.pick:
        wanted = Fake.pick
        Fake.pick = None

        def pick(widget):
            if isinstance(widget, Gtk.RadioButton) and widget.get_label() == wanted:
                widget.set_active(True)
            if isinstance(widget, Gtk.Container):
                for child in widget.get_children():
                    pick(child)
        pick(self)
    if Fake.response == 'ok':
        Fake.response = 'cancel'
        return Gtk.ResponseType.OK
    return Gtk.ResponseType.CANCEL


Gtk.Dialog.run = fake_dialog_run


def all_widgets(widget, found=None):
    found = [] if found is None else found
    found.append(widget)
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            all_widgets(child, found)
    return found


def button_text(button):
    if button.get_label():
        return button.get_label()
    texts = labels_of(button)
    return texts[0] if texts else ''


def find_button(root, text, prefix=False):
    for widget in all_widgets(root):
        if isinstance(widget, Gtk.Button) and not isinstance(widget, Gtk.LinkButton):
            label = button_text(widget)
            if label == text or (prefix and label.startswith(text)):
                return widget
    return None


def find_button_with_class(root, css_class):
    for widget in all_widgets(root):
        if isinstance(widget, Gtk.Button) and \
                css_class in widget.get_style_context().list_classes():
            return widget
    return None


def pump(seconds=1.0):
    end = time.time() + seconds
    while time.time() < end:
        while Gtk.events_pending():
            Gtk.main_iteration()
        time.sleep(0.02)


def wait_for(predicate, seconds=10.0):
    end = time.time() + seconds
    while time.time() < end and not predicate():
        pump(0.2)
    return bool(predicate())


def manager_for(fake_path, seen):
    backend = ui.Backend(str(fake_path))
    backend.fake['seen'] = seen
    window = ui.Manager(False, backend, palette='dark')
    window.show_all()
    if not wait_for(lambda: bool(window.gpus)):
        raise SystemExit('PROBE fail the fake Intel-only machine never loaded')
        raise SystemExit('PROBE fail the fake machine never loaded')
    return window


def shared_checks(window):
    """Every tab and the header buttons exist on every machine."""
    for page, text, _icon in ui.PAGES:
        window.go('overview')
        pump(0.3)
        find_button(window, text).emit('clicked')
        pump(0.5)
        check(f'tab "{text}" switches to its page',
              window.stack.get_visible_child_name() == page,
              window.stack.get_visible_child_name())
    before = window._renders
    find_button(window, 'Refresh').emit('clicked')
    check('Refresh re-reads the machine', wait_for(lambda: window._renders > before))
    dialogs = len(Fake.dialogs)
    find_button_with_class(window, 'icon-button').emit('clicked')
    pump(0.5)
    check('the info button opens an about dialog',
          len(Fake.dialogs) > dialogs and
          any('Nothing happens until you press a button' in ' '.join(texts)
              for texts in Fake.dialogs[dialogs:]),
          Fake.dialogs[dialogs:])
    window.go('overview')
    pump(0.5)
    dialogs = len(Fake.dialogs)
    find_button(window, 'Configure').emit('clicked')
    pump(0.5)
    check('Overview "Configure" opens the role dialog for the desktop card',
          len(Fake.dialogs) > dialogs and
          any('Set this role' in texts and window.gpus and 'Cancel' in texts
              for texts in Fake.dialogs[dialogs:]),
          Fake.dialogs[dialogs:])
    launched = len(Fake.popens)
    find_button(window, 'Display settings').emit('clicked')
    pump(0.5)
    check('Overview "Display settings" opens the display settings app',
          len(Fake.popens) > launched and
          any(any(part.endswith('mate-display-properties') for part in started)
              for started in Fake.popens[launched:]),
          Fake.popens[launched:])


def intel_checks(window):
    """The Intel-only PC: one card, so second-card actions must explain."""
    window.go('roles')
    pump(0.5)
    dialogs = len(Fake.dialogs)
    find_button(window, 'Change role', prefix=True).emit('clicked')
    pump(0.5)
    check('Roles "Change role" opens the role dialog with the four roles',
          len(Fake.dialogs) > dialogs and
          all(any(role in texts for role in ('Desktop', 'AI & compute', 'Games', 'Off'))
              for texts in Fake.dialogs[dialogs:]),
          Fake.dialogs[dialogs:])
    undo = find_button(window, 'Undo')
    check('Roles "Undo" says why it is not available',
          undo is not None and not undo.get_sensitive() and
          bool(undo.get_tooltip_text()),
          f'button={undo} tooltip={undo.get_tooltip_text() if undo else None}')
    dialogs = len(Fake.dialogs)
    Fake.response = 'ok'
    Fake.pick = 'AI & compute'
    find_button(window, 'Change role', prefix=True).emit('clicked')
    pump(0.5)
    check('a different role on the only card is explained, not applied',
          len(Fake.dialogs) > dialogs and
          any('Only one graphics card' in ' '.join(texts)
              for texts in Fake.dialogs[dialogs:]) and
          not window.backend.fake['roles'],
          Fake.dialogs[dialogs:])
    check('the one card is shown as the Desktop card',
          window.role_of(window.gpus[0]) == 'Desktop',
          window.role_of(window.gpus[0]))
    move_labels = labels_of(window.move_box)
    check('Move page explains a single-card PC in plain words',
          any('Only one graphics card' in text for text in move_labels),
          move_labels)
    check('Move page has no buttons when there is nothing to move',
          not [widget for widget in all_widgets(window.move_box)
               if isinstance(widget, Gtk.Button)])
    window.go('drivers')
    pump(0.5)
    check('Drivers page says no NVIDIA driver is installed',
          any('no driver installed' in text for text in labels_of(window.drivers_box)),
          labels_of(window.drivers_box))
    dialogs = len(Fake.dialogs)
    find_button(window, 'Check graphics').emit('clicked')
    pump(0.5)
    check('"Check graphics" reports something',
          len(Fake.dialogs) > dialogs and
          any('Graphics check' in texts for texts in Fake.dialogs[dialogs:]),
          Fake.dialogs[dialogs:])
    dialogs, launched = len(Fake.dialogs), len(Fake.popens)
    find_button(window, 'Install NVIDIA driver').emit('clicked')
    pump(0.5)
    check('"Install NVIDIA driver" explains there is no NVIDIA card',
          len(Fake.dialogs) > dialogs and
          any('no nvidia card' in ' '.join(texts).lower()
              for texts in Fake.dialogs[dialogs:]) and len(Fake.popens) == launched,
          Fake.dialogs[dialogs:])
    dialogs, launched = len(Fake.dialogs), len(Fake.popens)
    find_button(window, 'Install / repair AMD drivers').emit('clicked')
    pump(0.5)
    check('"Install / repair AMD drivers" explains there is no AMD card',
          len(Fake.dialogs) > dialogs and
          any('no amd graphics card' in ' '.join(texts).lower()
              for texts in Fake.dialogs[dialogs:]) and len(Fake.popens) == launched,
          Fake.dialogs[dialogs:])
    dialogs = len(Fake.dialogs)
    privileged = len(Fake.privileged)
    find_button(window, 'Restore graphics').emit('clicked')
    pump(0.5)
    check('"Restore graphics" asks for authentication and reports back',
          len(Fake.privileged) > privileged and
          Fake.privileged[-1][0] == 'pkexec' and len(Fake.dialogs) > dialogs,
          Fake.privileged[privileged:])
    links = [widget for widget in all_widgets(window.drivers_box)
             if isinstance(widget, Gtk.LinkButton)]
    check('the help links are real links (never clicked here)',
          len(links) == 3 and all(widget.get_uri().startswith('https://')
                                  for widget in links),
          [widget.get_uri() for widget in links])
    dialogs = len(Fake.dialogs)
    find_button(window, 'Copy log').emit('clicked')
    pump(0.5)
    check('"Copy log" tells you what it did',
          len(Fake.dialogs) > dialogs and
          any('Driver log' in texts for texts in Fake.dialogs[dialogs:]),
          Fake.dialogs[dialogs:])


def multi_checks(window):
    """The fake multi-card machine (bigboy) must keep working: a second card
    still takes a role, Undo puts it back, Move still has its buttons and the
    NVIDIA installer still opens."""
    cards = [child for child in window.cards_box.get_children()
             if isinstance(child, ui.Card)]
    check('multi-card Overview shows every card', len(cards) == 3,
          [child.gpu['name'] for child in cards])
    window.go('roles')
    pump(0.5)
    dialogs = len(Fake.dialogs)
    Fake.response = 'ok'
    Fake.pick = 'AI & compute'
    find_button(window, 'Change role', prefix=True).emit('clicked')
    pump(0.5)
    applied = window.backend.fake['roles']
    check('a different role on a second card is applied',
          applied.get('0000:01:00.0') == 'AI & compute' and
          not any('Only one graphics card' in ' '.join(texts)
                  for texts in Fake.dialogs[dialogs:]),
          f'roles={applied} dialogs={Fake.dialogs[dialogs:]}')
    undo = find_button(window, 'Undo')
    check('Undo appears for the changed card', undo is not None and
          undo.get_sensitive(), str(undo))
    if undo and undo.get_sensitive():
        undo.emit('clicked')
        pump(0.5)
        check('Undo puts the old role back',
              window.backend.fake['roles'].get('0000:01:00.0') == 'Desktop',
              window.backend.fake['roles'])
    window.go('move')
    pump(0.5)
    step_buttons = [widget for widget in all_widgets(window.move_box)
                    if isinstance(widget, Gtk.Button)]
    check('Move page still offers the three steps',
          len(step_buttons) >= 2 and
          find_button(window, 'Use it for the desktop') is not None,
          [button_text(button) for button in step_buttons])
    window.go('drivers')
    pump(0.5)
    launched = len(Fake.popens)
    find_button(window, 'Replace working NVIDIA driver').emit('clicked')
    pump(0.5)
    check('the NVIDIA installer opens on a machine with an NVIDIA card',
          len(Fake.popens) > launched and
          any(any('spaced-nvidia-installer' in part for part in started)
              for started in Fake.popens[launched:]),
          Fake.popens[launched:])


def icon_fallback_check():
    with tempfile.TemporaryDirectory() as empty:
        os.environ['SPACED_GPU_MANAGER_ASSETS'] = empty
        for image in ui.tinted_images():
            image.reload()
        missing = [image.icon_name for image in ui.tinted_images()
                   if image.get_storage_type() != Gtk.ImageType.ICON_NAME
                   or not image.get_icon_name()
                   or image.get_icon_name() == 'image-missing']
        del os.environ['SPACED_GPU_MANAGER_ASSETS']
        check('missing icon files fall back to themed icons, never no-entry',
              not missing, missing)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--fake-data', required=True)
    parser.add_argument('--multi', action='store_true',
                        help='check the multi-card machine instead of Intel-only')
    args = parser.parse_args()
    fake_path = Path(args.fake_data)

    ui.subprocess.run = fake_run
    ui.subprocess.Popen = fake_popen
    ui.shutil.which = lambda command: '/usr/bin/' + command

    window = manager_for(fake_path, seen=bool(args.multi))
    if not args.multi:
        check('fresh PC shows the first-run card',
              window.stack.get_visible_child_name() == 'first-run',
              window.stack.get_visible_child_name())
        cards = [child for child in window.cards_box.get_children()
                 if isinstance(child, ui.Card)]
        check('Overview shows the Intel card, not only the first-run card',
              any(child.gpu['name'] == 'Intel UHD Graphics 630' for child in cards),
              [child.gpu['name'] for child in cards])
        find_button(window, 'Look around').emit('clicked')
        pump(1.0)
        check('"Look around" opens Overview',
              window.stack.get_visible_child_name() == 'overview',
              window.stack.get_visible_child_name())
        chooser = manager_for(fake_path, seen=False)
        find_button(chooser, 'Choose my setup').emit('clicked')
        pump(1.0)
        check('"Choose my setup" opens Card roles',
              chooser.stack.get_visible_child_name() == 'roles',
              chooser.stack.get_visible_child_name())
        chooser.set_visible(False)

    shared_checks(window)
    if args.multi:
        multi_checks(window)
    else:
        intel_checks(window)
    icon_fallback_check()
    check('nothing privileged ran: only recorded pkexec and the read-only audit',
          all(argv[0] == 'pkexec' or argv == [ui.NVIDIA_HELPER, '--audit']
              for argv in Fake.privileged),
          Fake.privileged)

    if FAILED:
        print(f'PROBE FAILED ({len(FAILED)}): ' + '; '.join(FAILED), flush=True)
        return 1
    print('PROBE_ALL_OK', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
