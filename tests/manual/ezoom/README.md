# Fractional-wheel regression probe

Run only inside a disposable X11/Compiz desktop VM. The root helper creates
a virtual mouse; do not run it on a working host desktop. Install
`python3-pyqt5 python3-evdev xdotool` in the VM first.

1. Copy both Python files to the VM. As the desktop user, run
   `python3 qt-wheel.py`. Keep the pointer over its text area.
2. As root, run `python3 wheel-device.py`. Wait for
   `/tmp/wheel-device-ready` to appear. This helper exits after 30 minutes;
   Ctrl+C also stops it and removes the virtual device.
3. As the desktop user, empty `/tmp/qt-wheel-events.log`, hold Super+Shift,
   and run `touch /tmp/wheel-trigger` from a second terminal. The helper emits
   eight fractional scroll steps of 15/120 each and the matching core event.
   The desktop must zoom, with **zero** `wheel` lines in the log.
4. Release the modifiers and trigger again: expect eight Qt wheel events.
   Repeat with an additional Control modifier: expect eight events, because
   that chord does not match the configured zoom binding.
5. Repeat suppression after returning to Super+Shift. While holding that
   chord, change both ezoom wheel bindings to Control+Super in CCSM: scrolling
   must reach Qt. Restore the bindings: it must be suppressed again.
6. Disable ezoom while the chord is held: scrolling must reach Qt. Release
   the modifiers, re-enable ezoom, hold them again and confirm suppression.
   Finally release all modifiers and confirm normal scrolling resumes.

Allow three seconds after each configuration change for Compiz's settings
backend. Repeat the sequence to check for a stuck grab. Confirm ordinary
mouse clicks and other Compiz shortcuts still work after releasing the chord.
The unpatched package reproduces the bug with this probe: Qt records eight
fractional events while the desktop zooms.
