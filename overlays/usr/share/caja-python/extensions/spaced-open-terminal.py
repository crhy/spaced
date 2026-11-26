# Spaced Linux: "Open Terminal…" on a Caja folder's right-click menu (issue #302).
# First-party replacement for the upstream caja-open-terminal C plugin, which the
# image no longer installs. The folder is handed to the terminal as its working
# directory, never as part of a shell command line.
import os
import shutil
import subprocess
from urllib.parse import unquote, urlparse

from gi.repository import Caja, GObject

# Resolved in the order Spaced desktop apps resolve their tools: the MATE
# terminal, then the Debian terminal alternative, then the host's terminal
# through flatpak-spawn when Caja itself runs inside a Flatpak sandbox.
TERMINAL_NAMES = ("mate-terminal", "x-terminal-emulator")


class SpacedOpenTerminal(GObject.GObject, Caja.MenuProvider):
    def __init__(self):
        GObject.GObject.__init__(self)
        self._terminal = None

    @staticmethod
    def _local_folder(files):
        if len(files) != 1:
            return None
        parsed = urlparse(files[0].get_uri())
        if parsed.scheme != "file" or parsed.netloc not in ("", "localhost"):
            return None
        path = unquote(parsed.path)
        return path if os.path.isdir(path) else None

    def _resolve_terminal(self):
        if self._terminal is not None:
            return self._terminal
        for name in TERMINAL_NAMES:
            if shutil.which(name):
                self._terminal = [name]
                return self._terminal
        if shutil.which("flatpak-spawn"):
            # The sandbox's PATH has no host terminal, so ask the host for one
            # and start it there, exactly as Spaced Update does for host tools.
            for name in TERMINAL_NAMES:
                try:
                    probe = subprocess.run(
                        ["flatpak-spawn", "--host", "which", name],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=5,
                    )
                except (OSError, subprocess.SubprocessError):
                    continue
                if probe.returncode == 0:
                    self._terminal = ["flatpak-spawn", "--host", name]
                    return self._terminal
        self._terminal = []
        return self._terminal

    def get_file_items(self, window, files):
        path = self._local_folder(files)
        if path is None:
            return []
        item = Caja.MenuItem(
            name="SpacedOpenTerminal::open",
            label="Open Terminal…",
            tip="Open a terminal in this folder",
            icon="gnome-terminal",
        )
        if not self._resolve_terminal():
            # Nothing installed can open a terminal: keep the action visible
            # but inactive, so the menu does not promise a dead click.
            item.set_property("sensitive", False)
        item.connect("activate", self.on_activate, path)
        return [item]

    def on_activate(self, menu_item, path):
        terminal = self._resolve_terminal()
        if not terminal:
            return
        try:
            subprocess.Popen(terminal, cwd=path, close_fds=True)
        except OSError:
            pass
