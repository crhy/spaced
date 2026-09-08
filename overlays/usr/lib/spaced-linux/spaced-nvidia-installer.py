#!/usr/bin/python3
import getpass
import subprocess
import threading
from pathlib import Path
from typing import Optional

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk
from spaced_nvidia_state import awaiting_reboot, installation_verified

HELPER = "/usr/lib/spaced-linux/spaced-nvidia-helper"
LOG_FILE = "/var/log/spaced-nvidia-installer.log"
PENDING_FILE = Path("/var/lib/spaced-nvidia-installer/reboot-required")

ERRORS = {
    3: "Administrator authentication is required.",
    10: "Secure Boot is enabled. Disable it in firmware, boot Spaced Linux again, and rerun the installer.",
    11: "This installer currently supports amd64 computers.",
    12: "No NVIDIA graphics card was detected.",
    13: "The desktop user account could not be identified.",
    14: "There is not enough free space on the root filesystem.",
    15: "There is not enough free space for the boot image.",
    16: "Package information could not be downloaded.",
    20: "The exact header package for the running kernel is unavailable.",
    21: "A required Devuan package is unavailable or could not be installed.",
    22: "NVIDIA's official Debian repository could not be enabled.",
    23: "NVIDIA Driver Assistant is unavailable.",
    24: "NVIDIA Driver Assistant does not support this system or GPU.",
    30: "The NVIDIA package installation failed. Review the recovery result in the log.",
    40: "The NVIDIA kernel modules were not built. Review the recovery result in the log.",
    41: "The boot image could not be rebuilt. Review the recovery result in the log.",
    42: "A configuration rule still blocks an NVIDIA module. Review the recovery result in the log.",
    43: "Nouveau could not be disabled safely. Review the recovery result in the log.",
    44: "The rebuilt boot image does not contain every NVIDIA module. Review the recovery result in the log.",
    45: "The NVIDIA Xorg or GLX userspace installation is incomplete. Review the recovery result in the log.",
    46: "Compiz integration is incomplete. Review the recovery result in the log.",
    47: "The final GRUB graphics configuration is unsafe. Review the recovery result in the log.",
    50: "No verified NVIDIA installation is awaiting reboot.",
    51: "No NVIDIA installation transaction is available to roll back.",
    52: "Graphics recovery is incomplete. Repair the failed steps before rebooting.",
}


class Installer(Gtk.Window):
    def __init__(self) -> None:
        super().__init__(title="Spaced Video Drivers")
        self.running = False
        self.last_error: Optional[str] = None
        self.last_error_code: Optional[int] = None
        self.user = getpass.getuser()
        self.set_default_size(800, 600)
        self.set_border_width(18)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.connect("delete-event", self.on_delete)
        self.connect("destroy", Gtk.main_quit)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        Gtk.Window.add(self, root)

        heading = Gtk.Label()
        heading.set_markup('<span size="xx-large" weight="bold">Spaced Video Drivers</span>')
        heading.set_xalign(0)
        root.pack_start(heading, False, False, 0)

        subtitle = Gtk.Label(
            label=(
                "Installs the NVIDIA-recommended driver as a verified transaction, removes conflicting "
                "blacklists, disables Nouveau only after the NVIDIA modules exist, prepares Compiz, and "
                "checks the complete desktop after reboot."
            )
        )
        subtitle.set_xalign(0)
        subtitle.set_line_wrap(True)
        root.pack_start(subtitle, False, False, 0)

        self.gpu = self.detect_gpu()
        self.has_nvidia = bool(self.gpu and any(name in self.gpu.lower() for name in ("nvidia", "[10de:")))
        self.has_amd = bool(self.gpu and any(name in self.gpu.lower() for name in ("amd", "ati", "[1002:")))
        frame = Gtk.Frame(label="Detected hardware")
        root.pack_start(frame, False, False, 0)
        gpu_label = Gtk.Label(label=self.gpu or "No graphics device was detected.")
        gpu_label.set_xalign(0)
        gpu_label.set_line_wrap(True)
        gpu_label.set_margin_start(12)
        gpu_label.set_margin_end(12)
        gpu_label.set_margin_top(8)
        gpu_label.set_margin_bottom(8)
        frame.add(gpu_label)

        details = Gtk.Label(
            label=(
                "Before reboot, Spaced verifies exact kernel headers, Secure Boot, package availability, "
                "DKMS modules, modprobe policy, initramfs contents, NVIDIA Xorg libraries, GRUB arguments, "
                "and the Compiz session launcher. After reboot, it verifies PCI binding, nvidia-smi, NVIDIA "
                "OpenGL, Compiz, the MATE panel, and Caja."
            )
        )
        details.set_xalign(0)
        details.set_line_wrap(True)
        root.pack_start(details, False, False, 0)

        self.progress = Gtk.ProgressBar()
        self.progress.set_show_text(True)
        self.progress.set_text("Ready")
        root.pack_start(self.progress, False, False, 0)

        scroller = Gtk.ScrolledWindow()
        scroller.set_hexpand(True)
        scroller.set_vexpand(True)
        root.pack_start(scroller, True, True, 0)
        self.text = Gtk.TextView()
        self.text.set_editable(False)
        self.text.set_cursor_visible(False)
        self.text.set_monospace(True)
        self.buffer = self.text.get_buffer()
        scroller.add(self.text)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        root.pack_start(buttons, False, False, 0)

        self.audit_button = Gtk.Button(label="Check Graphics")
        self.audit_button.connect("clicked", lambda *_: self.start_action("--audit"))
        buttons.pack_start(self.audit_button, False, False, 0)
        self.amd_button = Gtk.Button(label="Update AMD Drivers")
        self.amd_button.connect("clicked", lambda *_: self.start_action("--install-amd"))
        self.amd_button.set_sensitive(self.has_amd)
        buttons.pack_start(self.amd_button, False, False, 0)
        self.install_button = Gtk.Button(label="Install NVIDIA Driver")
        self.install_button.connect("clicked", self.confirm_install)
        self.install_button.set_sensitive(self.has_nvidia and (not PENDING_FILE.exists() or installation_verified(PENDING_FILE)))
        buttons.pack_start(self.install_button, True, True, 0)

        self.rollback_button = Gtk.Button(label="Restore Graphics")
        self.rollback_button.connect("clicked", self.confirm_rollback)
        self.rollback_button.set_sensitive(self.has_nvidia)
        buttons.pack_start(self.rollback_button, False, False, 0)

        self.copy_button = Gtk.Button(label="Copy Log")
        self.copy_button.connect("clicked", self.copy_log)
        buttons.pack_start(self.copy_button, False, False, 0)

        self.close_button = Gtk.Button(label="Close")
        self.close_button.connect("clicked", lambda *_: self.close())
        buttons.pack_start(self.close_button, False, False, 0)

        support = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        for label, url in (("Online Help", "https://spacedlinux.com/help.html"),
                           ("Discord", "https://discord.gg/BMW9Y6NB3y"),
                           ("Telegram", "https://t.me/+pjmFzHo-i9A2ZWY5")):
            support.pack_start(Gtk.LinkButton.new_with_label(url, label), False, False, 0)
        root.pack_start(support, False, False, 0)

        if PENDING_FILE.exists() and awaiting_reboot(PENDING_FILE):
            self.progress.set_fraction(1.0)
            self.progress.set_text("Verified installation awaiting reboot")
            GLib.idle_add(self.show_reboot_dialog)
        elif installation_verified(PENDING_FILE):
            self.progress.set_fraction(1.0)
            self.progress.set_text("NVIDIA driver verified after reboot")
        elif PENDING_FILE.exists():
            self.progress.set_text("NVIDIA startup verification is pending — review the startup report")
        elif not self.gpu:
            self.progress.set_text("No graphics device detected")

    @staticmethod
    def detect_gpu() -> Optional[str]:
        try:
            result = subprocess.run(["lspci", "-nn"], check=False, capture_output=True, text=True, errors="replace")
        except OSError:
            return None
        devices = []
        for line in result.stdout.splitlines():
            lower = line.lower()
            if any(kind in lower for kind in ("vga compatible controller", "3d controller", "display controller")):
                devices.append(line.strip())
        return "\n".join(devices) or None

    def on_delete(self, *_args) -> bool:
        if not self.running:
            return False
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.CLOSE,
            text="Installation is still running",
        )
        dialog.format_secondary_text("Wait for the installer to finish or restore the previous configuration before closing it.")
        dialog.run()
        dialog.destroy()
        return True

    def append_log(self, text: str) -> bool:
        if not text:
            return False
        self.buffer.insert(self.buffer.get_end_iter(), text + "\n")
        mark = self.buffer.create_mark(None, self.buffer.get_end_iter(), False)
        self.text.scroll_mark_onscreen(mark)
        return False

    def pulse(self) -> bool:
        if not self.running:
            return False
        self.progress.pulse()
        return True

    def set_busy(self, busy: bool) -> None:
        self.running = busy
        self.install_button.set_sensitive(not busy and self.has_nvidia and (not PENDING_FILE.exists() or installation_verified(PENDING_FILE)))
        self.rollback_button.set_sensitive(not busy and self.has_nvidia)
        self.audit_button.set_sensitive(not busy)
        self.amd_button.set_sensitive(not busy and self.has_amd)
        self.close_button.set_sensitive(not busy)

    def confirm_install(self, *_args) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.NONE,
            text="Install and verify the NVIDIA driver?",
        )
        dialog.format_secondary_text(
            "Spaced Linux will not disable Nouveau until the NVIDIA modules are built. Any failed verification "
            "before reboot triggers an automatic rollback. The computer will reboot only after you approve it."
        )
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Install", Gtk.ResponseType.OK)
        response = dialog.run()
        dialog.destroy()
        if response == Gtk.ResponseType.OK:
            self.start_action("--install")

    def confirm_rollback(self, *_args) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.NONE,
            text="Restore Graphics?",
        )
        dialog.format_secondary_text("This removes packages installed by the last Spaced NVIDIA transaction, restores the saved graphics configuration, rebuilds the boot image, and then offers to reboot.")
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Restore Graphics", Gtk.ResponseType.OK)
        response = dialog.run()
        dialog.destroy()
        if response == Gtk.ResponseType.OK:
            self.start_action("--rollback")

    def start_action(self, mode: str) -> None:
        if self.running:
            return
        self.set_busy(True)
        self.last_error = None
        self.last_error_code = None
        self.buffer.set_text("")
        self.progress.set_fraction(0.05)
        self.progress.set_text("Checking graphics…" if mode == "--audit" else "Requesting administrator authentication…")
        GLib.timeout_add(120, self.pulse)
        threading.Thread(target=self.run_action, args=(mode,), daemon=True).start()

    def process_line(self, line: str) -> bool:
        if line.startswith("SPACED_STATUS:"):
            text = line.partition(":")[2]
            self.progress.set_text(text)
            self.append_log(text)
        elif line.startswith("SPACED_WARNING:"):
            self.append_log("WARNING: " + line.partition(":")[2])
        elif line.startswith("SPACED_ERROR:"):
            fields = line.split(":", 2)
            if len(fields) == 3:
                try:
                    self.last_error_code = int(fields[1])
                except ValueError:
                    self.last_error_code = None
                self.last_error = fields[2]
        elif line.startswith("SPACED_SUCCESS:"):
            self.append_log("Requested graphics operation completed.")
        else:
            self.append_log(line)
        return False

    def run_action(self, mode: str) -> None:
        command = ["pkexec", HELPER, mode, "--desktop-user", self.user]
        if mode == "--audit":
            command = [HELPER, mode]
        try:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace", bufsize=1)
            if process.stdout is not None:
                for line in process.stdout:
                    GLib.idle_add(self.process_line, line.rstrip())
            code = process.wait()
        except OSError as exc:
            GLib.idle_add(self.finish_action, mode, 125, str(exc))
            return
        GLib.idle_add(self.finish_action, mode, code, None)

    def finish_action(self, mode: str, code: int, startup_error: Optional[str]) -> bool:
        self.set_busy(False)
        self.progress.set_fraction(1.0)
        if code == 0:
            if mode == "--audit":
                self.progress.set_text("Graphics report ready — use Copy Log to save it")
            elif mode == "--install-amd":
                self.progress.set_text("AMD graphics packages updated — reboot to use them")
            elif mode == "--install":
                self.progress.set_text("Installation verified — reboot required")
                self.install_button.set_sensitive(False)
                self.show_reboot_dialog()
            else:
                self.progress.set_text("Saved graphics configuration restored — reboot required")
                self.show_reboot_dialog(restored=True)
            return False

        if code in (126, 127):
            message = "Administrator authentication was cancelled."
        elif startup_error:
            message = startup_error
        elif self.last_error:
            message = self.last_error
        else:
            message = ERRORS.get(code, f"The installer stopped with status {code}. Review {LOG_FILE}.")
        self.progress.set_text("Graphics recovery is incomplete" if self.last_error_code == 52 or code == 52 else "Graphics operation did not complete")
        self.show_error(message)
        return False

    def show_error(self, message: str) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.CLOSE,
            text="Graphics operation did not complete",
        )
        dialog.format_secondary_text(message + f"\n\nDetailed log: {LOG_FILE}")
        dialog.run()
        dialog.destroy()

    def show_reboot_dialog(self, restored: bool = False) -> bool:
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.NONE,
            text="Reboot required",
        )
        if restored:
            dialog.format_secondary_text("The saved graphics configuration and package recovery steps completed. Reboot now to activate them.")
        else:
            dialog.format_secondary_text(
                "The NVIDIA modules, module policy, initramfs, Xorg libraries, GRUB settings, and Compiz launcher all passed verification. After login, Spaced Linux will verify the running NVIDIA desktop."
            )
        dialog.add_button("Reboot Later", Gtk.ResponseType.CANCEL)
        dialog.add_button("Reboot Now", Gtk.ResponseType.OK)
        response = dialog.run()
        dialog.destroy()
        if response == Gtk.ResponseType.OK:
            self.request_reboot()
        else:
            self.progress.set_text("Reboot when ready")
        return False

    def request_reboot(self) -> None:
        self.set_busy(True)
        self.progress.set_text("Requesting reboot…")
        threading.Thread(target=self.run_reboot, daemon=True).start()

    def run_reboot(self) -> None:
        result = subprocess.run(["pkexec", HELPER, "--reboot", "--desktop-user", self.user], check=False, capture_output=True, text=True, errors="replace")
        if result.returncode != 0:
            message = result.stdout.strip() or result.stderr.strip() or "The reboot request was cancelled."
            GLib.idle_add(self.reboot_failed, message)

    def reboot_failed(self, message: str) -> bool:
        self.set_busy(False)
        self.progress.set_text("Reboot manually when ready")
        self.show_error(message)
        return False

    def copy_log(self, *_args) -> None:
        start = self.buffer.get_start_iter()
        end = self.buffer.get_end_iter()
        text = self.buffer.get_text(start, end, True)
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(text, -1)
        clipboard.store()


if __name__ == "__main__":
    window = Installer()
    window.show_all()
    Gtk.main()
