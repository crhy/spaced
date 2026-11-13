#!/usr/bin/python3
import os
import pwd
import subprocess
import time
from pathlib import Path

from spaced_nvidia_state import PENDING, ack_path, awaiting_reboot, marker_id

HELPER = "/usr/lib/spaced-linux/spaced-nvidia-helper"
LOG_FILE = "/var/log/spaced-nvidia-installer.log"
FULL_TIMEOUT = 15
QUICK_TIMEOUT = 3
SESSION_DEADLINE = 60


def load_gtk():
    """Import GTK only when a dialog is really needed.

    Most logins have no pending driver install, so autostart must not pay for
    GObject-Introspection and GTK before the marker check in main().
    """
    import gi

    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    return Gtk


def run(command, timeout=FULL_TIMEOUT):
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            env={**os.environ, "LC_ALL": "C"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 125, "", str(exc)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def check_opengl():
    details, failures = [], []
    rc, output, error = run(["glxinfo", "-B"])
    details.append("Desktop OpenGL:\n" + (output or error or "No output"))
    lowered = output.lower()
    if rc != 0 or "opengl renderer string:" not in lowered:
        failures.append("Desktop OpenGL renderer information could not be read.")
    if any(token in lowered for token in ("llvmpipe", "softpipe", "software rasterizer")):
        failures.append("Desktop OpenGL is using software rendering.")
    if "direct rendering: yes" not in lowered:
        failures.append("Desktop OpenGL direct rendering is unavailable.")
    if "opengl vendor string: nvidia corporation" in lowered:
        return failures, details

    # Hybrid laptops normally keep the Intel/AMD GPU as the desktop renderer.
    # NVIDIA's documented PRIME variables verify the discrete GPU separately.
    rc, output, error = run([
        "env", "__NV_PRIME_RENDER_OFFLOAD=1", "__GLX_VENDOR_LIBRARY_NAME=nvidia",
        "glxinfo", "-B",
    ])
    details.append("NVIDIA PRIME OpenGL:\n" + (output or error or "No output"))
    lowered = output.lower()
    if (rc != 0 or "opengl vendor string: nvidia corporation" not in lowered
            or "direct rendering: yes" not in lowered
            or any(token in lowered for token in ("llvmpipe", "softpipe", "software rasterizer"))):
        failures.append("NVIDIA OpenGL could not be verified through PRIME render offload.")
    return failures, details


def collect_checks(quick_timeout=QUICK_TIMEOUT):
    """Run the whole check set once. `quick_timeout` bounds the cheap probes
    that are repeated while the session is still coming up."""
    details = []
    failures = []

    rc, output, error = run(["lspci", "-nnk", "-d", "10de:"])
    details.append("PCI driver:\n" + (output or error or "No NVIDIA PCI output"))
    if rc != 0 or "Kernel driver in use: nvidia" not in output:
        failures.append("The NVIDIA GPU is not bound to the nvidia kernel driver.")

    rc, output, error = run([
        "nvidia-smi",
        "--query-gpu=name,driver_version",
        "--format=csv,noheader",
    ])
    details.append("nvidia-smi:\n" + (output or error or "No output"))
    if rc != 0 or not output:
        failures.append("nvidia-smi could not communicate with the NVIDIA driver.")

    rc, output, error = run(["sh", "-c", "lsmod | grep -E '^(nvidia|nouveau)' || true"], timeout=quick_timeout)
    details.append("Loaded modules:\n" + (output or "No NVIDIA/Nouveau modules listed"))
    if not any(line.startswith("nvidia ") for line in output.splitlines()):
        failures.append("The core nvidia module is not loaded.")
    if any(line.startswith("nouveau ") for line in output.splitlines()):
        failures.append("Nouveau is still loaded after the NVIDIA reboot.")

    gl_failures, gl_details = check_opengl()
    failures.extend(gl_failures)
    details.extend(gl_details)

    rc, output, error = run(["wmctrl", "-m"], timeout=quick_timeout)
    details.append("Window manager:\n" + (output or error or "No output"))
    wm_name = ""
    if rc == 0:
        wm_name = next(
            (line.partition(":")[2].strip() for line in output.splitlines()
             if line.lower().startswith("name:")),
            "",
        )
    rc, compiz_out, _ = run(["pgrep", "-u", str(os.getuid()), "-x", "compiz"], timeout=quick_timeout)
    details.append("Compiz process: " + ("running" if rc == 0 and compiz_out else "not running"))
    if wm_name.lower() != "compiz":
        # wmctrl can miss the WM during the first seconds of a session or be
        # absent after a partial upgrade; the compositor process itself is the
        # fallback only when wmctrl could not name a window manager. If it
        # explicitly names another WM, a stray Compiz process is not success.
        if wm_name or rc != 0 or not compiz_out:
            failures.append("Compiz is not the active window manager.")

    for process, label in (("mate-panel", "MATE panel"), ("caja", "Caja desktop")):
        rc, output, _ = run(["pgrep", "-u", str(os.getuid()), "-x", process], timeout=quick_timeout)
        details.append(f"{label}: " + ("running" if rc == 0 and output else "not running"))
        if rc != 0 or not output:
            failures.append(f"{label} is not running.")

    return failures, "\n\n".join(details)


def wait_for_session(deadline_seconds=SESSION_DEADLINE):
    """Retry only the transient failures, and never for longer than the deadline."""
    deadline = time.monotonic() + deadline_seconds
    last = ([], "")
    while True:
        last = collect_checks(QUICK_TIMEOUT)
        failures, _ = last
        transient = [
            item
            for item in failures
            if "Compiz" in item or "panel" in item or "Caja" in item or "OpenGL" in item
        ]
        if not transient:
            return last
        if time.monotonic() >= deadline:
            return last
        time.sleep(1)


def show_success(details):
    Gtk = load_gtk()
    dialog = Gtk.MessageDialog(
        message_type=Gtk.MessageType.INFO,
        buttons=Gtk.ButtonsType.CLOSE,
        text="NVIDIA driver verified",
    )
    dialog.format_secondary_text(
        "The NVIDIA kernel driver, NVIDIA OpenGL, Compiz, the MATE panel, and Caja are all running correctly."
    )
    dialog.run()
    dialog.destroy()
    acknowledgement = ack_path(PENDING)
    acknowledgement.parent.mkdir(parents=True, exist_ok=True)
    acknowledgement.write_text(details + "\n", encoding="utf-8")


def show_failure(failures, details):
    Gtk = load_gtk()
    dialog = Gtk.MessageDialog(
        message_type=Gtk.MessageType.ERROR,
        buttons=Gtk.ButtonsType.NONE,
        text="NVIDIA startup verification failed",
    )
    dialog.format_secondary_text("\n".join(f"• {item}" for item in failures))
    dialog.add_button("Keep System Running", Gtk.ResponseType.CANCEL)
    dialog.add_button("Restore Graphics and Reboot", Gtk.ResponseType.OK)
    response = dialog.run()
    dialog.destroy()
    log_dir = Path.home() / ".cache" / "spaced-nvidia-installer"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / f"failed-{marker_id(PENDING)}.log").write_text(details + "\n", encoding="utf-8")
    if response == Gtk.ResponseType.OK:
        user = pwd.getpwuid(os.getuid()).pw_name
        run_recovery(user)
    elif response == Gtk.ResponseType.CANCEL:
        # "Keep System Running" means the user declined recovery: acknowledge this
        # failed verification so the modal is not repeated at every later login.
        acknowledgement = ack_path(PENDING)
        acknowledgement.parent.mkdir(parents=True, exist_ok=True)
        acknowledgement.write_text(details + "\n", encoding="utf-8")


def recovery_message(result):
    """Return the helper's own reason for a failed recovery, or None on success."""
    if result.returncode == 0:
        return None
    for line in (result.stdout or "").splitlines():
        if line.startswith("SPACED_ERROR:"):
            fields = line.split(":", 2)
            if len(fields) == 3 and fields[2].strip():
                return fields[2].strip()
    return f"Graphics recovery stopped with status {result.returncode}. Review {LOG_FILE}."


def run_recovery(user):
    """Ask the helper to restore graphics and report the result to the user."""
    try:
        result = subprocess.run(
            [
                "pkexec",
                HELPER,
                "--rollback",
                "--reboot-after",
                "--desktop-user",
                user,
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
        )
    except OSError as exc:
        show_recovery_error(f"The graphics recovery could not start: {exc}")
        return
    message = recovery_message(result)
    if message:
        show_recovery_error(message)


def show_recovery_error(message):
    Gtk = load_gtk()
    dialog = Gtk.MessageDialog(
        message_type=Gtk.MessageType.ERROR,
        buttons=Gtk.ButtonsType.CLOSE,
        text="Graphics recovery did not finish",
    )
    dialog.format_secondary_text(message)
    dialog.run()
    dialog.destroy()


def main():
    if not PENDING.is_file():
        return
    if ack_path(PENDING).exists() or awaiting_reboot(PENDING):
        return
    failures, details = wait_for_session()
    if failures:
        show_failure(failures, details)
    else:
        show_success(details)


if __name__ == "__main__":
    main()
