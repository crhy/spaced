#!/usr/bin/python3
"""Run with xvfb-run: read-only UI smoke test using actual PCI inventory."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

root = Path(__file__).resolve().parents[2]
lib = root / 'overlays/usr/lib/spaced-linux'
sys.path.insert(0, str(lib))
spec = importlib.util.spec_from_file_location('gpu_manager_ui', lib / 'spaced-gpu-manager.py')
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)
window = ui.Manager(preview=True)
window.show_all()
deadline = time.monotonic() + 30
while window.busy and time.monotonic() < deadline:
    while ui.Gtk.events_pending():
        ui.Gtk.main_iteration_do(False)
    time.sleep(.02)
assert not window.busy, 'Inventory did not finish'
assert not window.driver_button.get_sensitive(), 'Preview must not allow driver mutations'
assert window.get_title() == 'Spaced GPU Manager'
assert len(window.cards.get_children()) == max(1, len(window.gpus))

# Exercise the real modal and clipboard path without launching any application.
for card in window.gpus:
    if card['driver'] != 'nvidia' or not card.get('uuid'):
        continue
    def respond(response):
        for dialog in ui.Gtk.Window.list_toplevels():
            if isinstance(dialog, ui.Gtk.MessageDialog):
                dialog.response(response)
        return False
    def copy_then_close():
        respond(ui.Gtk.ResponseType.APPLY)
        ui.GLib.timeout_add(100, respond, ui.Gtk.ResponseType.CLOSE)
        return False
    ui.GLib.timeout_add(100, copy_then_close)
    window.compute(card)
    copied = ui.Gtk.Clipboard.get(ui.Gdk.SELECTION_CLIPBOARD).wait_for_text()
    assert copied == 'env CUDA_VISIBLE_DEVICES=' + card['uuid'], copied

with patch.object(ui, 'trial_state', return_value={'phase': 'trial', 'deadline_boot_seconds': 190}), \
     patch.object(ui, 'boot_seconds', return_value=100):
    window.update_trial()
    assert '1:30 remaining' in window.trial_bar.get_children()[0].get_text()
    assert not window.trial_bar.get_children()[1].get_children()[0].get_sensitive()
    keep_button = window.keep_button
    window.poll_trial()
    assert window.keep_button is keep_button, 'Countdown must preserve keyboard focus'
window.update_trial()
window.resize(880, 680)
for _ in range(20):
    while ui.Gtk.events_pending():
        ui.Gtk.main_iteration_do(False)
    time.sleep(.02)
width, height = window.get_size()
assert width <= 900 and height <= 700, (width, height)
image = ui.Gdk.pixbuf_get_from_window(window.get_window(), 0, 0, width, height)
destination = Path(tempfile.mkdtemp(prefix='spaced-gpu-ui-')) / 'preview.png'
image.savev(str(destination), 'png', [], [])
print(f'UI OK: {len(window.gpus)} GPUs, {width}x{height}; screenshot {destination}')
window.disconnect_by_func(ui.Gtk.main_quit)
window.destroy()
