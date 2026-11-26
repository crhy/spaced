# Spaced Linux: "Open in Terminal Here" in the Caja folder right-click menu (issue #302).
import os
import shutil
import subprocess
from urllib.parse import unquote, urlparse

from gi.repository import Caja, GObject


TERMINALS = (
    "mate-terminal",
    "gnome-terminal",
    "xfce4-terminal",
    "x-terminal-emulator",
)


class SpacedOpenTerminal(GObject.GObject, Caja.MenuProvider):
    def __init__(self):
        GObject.GObject.__init__(self)

    @staticmethod
    def _local_folder(files):
        if len(files) != 1:
            return None
        parsed = urlparse(files[0].get_uri())
        if parsed.scheme != "file" or parsed.netloc not in ("", "localhost"):
            return None
        path = unquote(parsed.path)
        if not os.path.isabs(path) or not os.path.isdir(path):
            return None
        return path

    def get_file_items(self, window, files):
        path = self._local_folder(files)
        if path is None:
            return []
        item = Caja.MenuItem(
            name="SpacedOpenTerminal::open",
            label="Open in Terminal Here",
            tip="Open a terminal in this folder",
            icon="utilities-terminal",
        )
        item.connect("activate", self.on_activate, path)
        return [item]

    def on_activate(self, menu_item, path):
        for terminal in TERMINALS:
            if shutil.which(terminal):
                try:
                    subprocess.Popen(
                        [terminal, "--working-directory", path],
                        close_fds=True,
                    )
                except OSError:
                    pass
                return
