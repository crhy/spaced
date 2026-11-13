# Spaced Linux: safe, style-aware Caja wallpaper action (issue #303).
import os
import subprocess
from urllib.parse import unquote, urlparse

from gi.repository import Caja, GObject


class SpacedSetWallpaper(GObject.GObject, Caja.MenuProvider):
    def __init__(self):
        GObject.GObject.__init__(self)

    @staticmethod
    def _local_image(files):
        if len(files) != 1:
            return None
        mime_type = files[0].get_mime_type()
        if not mime_type or not mime_type.startswith("image/"):
            return None
        parsed = urlparse(files[0].get_uri())
        if parsed.scheme != "file" or parsed.netloc not in ("", "localhost"):
            return None
        path = unquote(parsed.path)
        return path if os.path.isabs(path) else None

    def get_file_items(self, window, files):
        path = self._local_image(files)
        if path is None:
            return []
        item = Caja.MenuItem(
            name="SpacedSetWallpaper::set",
            label="Set as Wallpaper…",
            tip="Copy this image and choose how it fits the screen",
            icon="preferences-desktop-wallpaper",
        )
        item.connect("activate", self.on_activate, path)
        return [item]

    def on_activate(self, menu_item, path):
        try:
            subprocess.Popen(
                ["/usr/lib/spaced-linux/spaced-wallpaper-dialog", path],
                close_fds=True,
            )
        except OSError:
            pass
