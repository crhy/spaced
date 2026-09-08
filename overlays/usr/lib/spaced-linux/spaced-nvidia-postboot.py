#!/usr/bin/python3
import os
import pwd
import subprocess
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from spaced_nvidia_state import PENDING, ack_path, awaiting_reboot, marker_id

HELPER = "/usr/lib/spaced-linux/spaced-nvidia-helper"


def run(command, timeout=15):
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


def collect_checks():
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

    rc, output, error = run(["sh", "-c", "lsmod | grep -E '^(nvidia|nouveau)' || true"])
    details.append("Loaded modules:\n" + (output or "No NVIDIA/Nouveau modules listed"))
    if not any(line.startswith("nvidia ") for line in output.splitlines()):
        failures.append("The core nvidia module is not loaded.")
    if any(line.startswith("nouveau ") for line in output.splitlines()):
        failures.append("Nouveau is still loaded after the NVIDIA reboot.")

    gl_failures, gl_details = check_opengl()
    failures.extend(gl_failures)
    details.extend(gl_details)

    rc, output, error = run(["wmctrl", "-m"])
    details.append("Window manager:\n" + (output or error or "No output"))
    wm_name = ""
    if rc == 0:
        wm_name = next(
            (line.partition(":")[2].strip() for line in output.splitlines()
             if line.lower().startswith("name:")),
            "",
        )
    rc, compiz_out, _ = run(["pgrep", "-u", str(os.getuid()), "-x", "compiz"])
    details.append("Compiz process: " + ("running" if rc == 0 and compiz_out else "not running"))
    if wm_name.lower() != "compiz":
        # wmctrl can miss the WM during the first seconds of a session or be
        # absent after a partial upgrade; the compositor process itself is the
        # fallback only when wmctrl could not name a window manager. If it
        # explicitly names another WM, a stray Compiz process is not success.
        if wm_name or rc != 0 or not compiz_out:
            failures.append("Compiz is not the active window manager.")

    for process, label in (("mate-panel", "MATE panel"), ("caja", "Caja desktop")):
        rc, output, _ = run(["pgrep", "-u", str(os.getuid()), "-x", process])
        details.append(f"{label}: " + ("running" if rc == 0 and output else "not running"))
        if rc != 0 or not output:
            failures.append(f"{label} is not running.")

    return failures, "\n\n".join(details)


def wait_for_session():
    last = ([], "")
    for _ in range(45):
        last = collect_checks()
        failures, _ = last
        transient = [
            item
            for item in failures
            if "Compiz" in item or "panel" in item or "Caja" in item or "OpenGL" in item
        ]
        if not transient:
            return last
        time.sleep(1)
    return last


def show_success(details):
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
        subprocess.Popen([
            "pkexec",
            HELPER,
            "--rollback",
            "--reboot-after",
            "--desktop-user",
            user,
        ])


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
