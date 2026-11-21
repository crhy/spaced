#!/usr/bin/python3
"""Run with xvfb-run: read-only UI smoke test using actual PCI inventory."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import time

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
