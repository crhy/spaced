# Spaced Linux: "Change Theme…" in the Caja desktop right-click menu (issue #346).
# Opens the existing MATE Appearance Preferences dialog on its Theme page.
import subprocess
from gi.repository import Caja, GObject


class SpacedChangeTheme(GObject.GObject, Caja.MenuProvider):
    def __init__(self):
        GObject.GObject.__init__(self)

    def get_background_items(self, window, current_folder):
        if not current_folder.get_uri().startswith("x-caja-desktop:"):
            return []
        item = Caja.MenuItem(
            name="SpacedChangeTheme::change",
            label="Change Theme…",
            tip="Choose a Spaced Linux theme",
            icon="preferences-desktop-theme",
        )
        item.connect("activate", self.on_activate)
        return [item]

    def on_activate(self, menu_item):
        try:
            subprocess.Popen(["mate-appearance-properties", "--show-page=theme"])
        except OSError:
            pass
