#!/usr/bin/python3
"""Small first-run Flatpak chooser for Spaced Linux."""

import subprocess
import sys
import threading

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402


CSS = b"""
window.spaced-welcome, window.spaced-welcome box.app-surface {
  background-color: #17191c;
  color: #f4f4f4;
}
.hero-title { font-size: 28px; font-weight: 700; color: #f4f4f4; }
.hero-subtitle { font-size: 14px; color: #b8bbc2; }
.choice-card {
  background-image: none;
  background-color: #1f2329;
  border: 1px solid #3a3f47;
  border-radius: 10px;
  padding: 18px 20px;
  color: #f4f4f4;
  box-shadow: none;
}
.choice-card:hover { background-color: #262b33; border-color: #6e9de8; }
.choice-card:active { background-color: #171a1f; border-color: #4f6bb0; }
.choice-title { font-size: 20px; font-weight: 700; color: #f4f4f4; }
.choice-detail { font-size: 12px; color: #b8bbc2; }
.choice-icon { color: #6e9de8; }
.status { font-size: 11px; color: #9ea2aa; }
"""


class WelcomeWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="Welcome to Spaced Linux")
        self.set_name("spaced-welcome")
        self.get_style_context().add_class("spaced-welcome")
        self.set_default_size(720, 480)
        self.set_resizable(False)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_border_width(0)

        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            self.get_screen(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        surface = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        surface.get_style_context().add_class("app-surface")
        surface.set_border_width(36)
        self.add(surface)

        title = Gtk.Label(label="Welcome to Spaced Linux")
        title.get_style_context().add_class("hero-title")
        surface.pack_start(title, False, False, 0)

        subtitle = Gtk.Label(label="Choose how you’d like to add applications.")
        subtitle.get_style_context().add_class("hero-subtitle")
        subtitle.set_margin_top(6)
        subtitle.set_margin_bottom(24)
        surface.pack_start(subtitle, False, False, 0)

        self.suggested = self._choice(
            "system-software-install",
            "Install Suggested Apps",
            "SpacedBazaar · Voice2Text · Cards with Cats · Brutal Chess · Spaced Update · essentials",
        )
        self.suggested.connect("clicked", self._start_install, "suggested")
        surface.pack_start(self.suggested, True, True, 0)

        self.bazaar = self._choice(
            "system-software-update",
            "Open SpacedBazaar",
            "Install SpacedBazaar, then browse Flathub",
        )
        self.bazaar.set_margin_top(18)
        self.bazaar.connect("clicked", self._start_install, "bazaar")
        surface.pack_start(self.bazaar, True, True, 0)

        self.nvidia_btn = self._choice(
            "video-display",
            "Install NVIDIA Drivers",
            "Set up proprietary NVIDIA graphics drivers",
        )
        self.nvidia_btn.set_margin_top(18)
        self.nvidia_btn.connect("clicked", self._open_nvidia_installer)
        surface.pack_start(self.nvidia_btn, True, True, 0)

        status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        status_box.set_halign(Gtk.Align.CENTER)
        status_box.set_margin_top(18)
        self.spinner = Gtk.Spinner()
        status_box.pack_start(self.spinner, False, False, 0)
        self.status = Gtk.Label(label="Nothing is installed until you choose.")
        self.status.get_style_context().add_class("status")
        status_box.pack_start(self.status, False, False, 0)
        surface.pack_start(status_box, False, False, 0)

    @staticmethod
    def _choice(icon_name, heading, detail):
        button = Gtk.Button()
        button.get_style_context().add_class("choice-card")
        button.set_relief(Gtk.ReliefStyle.NONE)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=18)
        icon = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.DIALOG)
        icon.get_style_context().add_class("choice-icon")
        row.pack_start(icon, False, False, 0)

        copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        copy.set_valign(Gtk.Align.CENTER)
        title = Gtk.Label(label=heading, xalign=0)
        title.get_style_context().add_class("choice-title")
        detail_label = Gtk.Label(label=detail, xalign=0)
        detail_label.get_style_context().add_class("choice-detail")
        copy.pack_start(title, False, False, 0)
        copy.pack_start(detail_label, False, False, 0)
        row.pack_start(copy, True, True, 0)

        arrow = Gtk.Label(label="›")
        arrow.get_style_context().add_class("choice-title")
        row.pack_end(arrow, False, False, 0)
        button.add(row)
        return button

    def _open_nvidia_installer(self, button):
        subprocess.Popen(
            ["spaced-nvidia-installer"],
            start_new_session=True,
        )

    def _start_install(self, _button, mode):
        self.suggested.set_sensitive(False)
        self.bazaar.set_sensitive(False)
        self.spinner.show()
        self.spinner.start()
        if mode == "suggested":
            self.status.set_text("Installing the suggested apps from Flathub…")
        else:
            self.status.set_text("Installing SpacedBazaar from GitHub…")
        threading.Thread(target=self._install, args=(mode,), daemon=True).start()

    def _install(self, mode):
        result = subprocess.run(
            ["/usr/local/bin/spaced-install-apps", mode],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        GLib.idle_add(self._finish_install, mode, result.returncode, result.stdout)

    def _finish_install(self, mode, returncode, output):
        self.spinner.stop()
        self.spinner.hide()
        self.suggested.set_sensitive(True)
        self.bazaar.set_sensitive(True)
        if returncode != 0:
            # Installer diagnostics can end with a very long app ID or URL.
            # Send those details to the session log instead of putting a raw
            # download URL into the small status label.
            if output.strip():
                print(output.rstrip(), file=sys.stderr)
            if mode == "bazaar":
                message = "SpacedBazaar could not be installed. Check your connection and try again."
            else:
                message = "Some suggested apps could not be installed. Check your connection and try again."
            self.status.set_text(message)
            return False

        if mode == "bazaar":
            self.status.set_text("SpacedBazaar is opening…")
            subprocess.Popen(
                ["flatpak", "run", "io.github.crhy.SpacedBazaar"],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            GLib.timeout_add(900, self.destroy)
        else:
            self.status.set_text("Your suggested apps are ready.")
        return False


def main():
    window = WelcomeWindow()
    window.connect("destroy", Gtk.main_quit)
    window.show_all()
    window.spinner.hide()
    Gtk.main()


if __name__ == "__main__":
    main()
