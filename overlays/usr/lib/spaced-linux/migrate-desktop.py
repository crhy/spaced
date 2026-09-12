#!/usr/bin/python3
"""Apply versioned, atomic desktop fixes to existing accounts on login."""

import configparser
import fcntl
import io
import os
from pathlib import Path
import shutil
import sys
import tempfile


IMAGE_TYPES = (
    "image/bmp", "image/gif", "image/jpeg", "image/jpg", "image/pjpeg",
    "image/png", "image/tiff", "image/webp", "image/svg+xml",
    "image/svg+xml-compressed", "image/vnd.microsoft.icon", "image/x-icon",
    "image/x-bmp", "image/x-MS-bmp", "image/x-png", "image/x-portable-anymap",
    "image/x-portable-bitmap", "image/x-portable-graymap", "image/x-portable-pixmap",
    "image/x-xbitmap", "image/x-xpixmap", "image/x-tga", "image/jp2",
    "image/jpeg2000", "image/jpx", "image/x-icns", "image/vnd.wap.wbmp",
)
# Script files are plain text to a desktop user. Issue #182 reported that
# Pluma was not retained for bash and Python files; the Python and shell alias
# types were simply never declared, so each launch fell back to whatever the
# shared MIME database guessed.
TEXT_TYPES = (
    "text/plain",
    "text/x-shellscript", "application/x-shellscript",
    "text/x-sh", "application/x-sh",
    "text/x-python", "text/x-python3",
    "text/x-perl", "application/x-perl",
)
BROWSERS = {
    "com.brave.Browser.desktop", "brave-browser.desktop", "firefox.desktop",
    "org.mozilla.firefox.desktop", "chromium.desktop", "google-chrome.desktop",
    "epiphany.desktop", "org.gnome.Epiphany.desktop",
}
FALLBACKS = {mime: "eom.desktop" for mime in IMAGE_TYPES}
FALLBACKS.update({mime: "pluma.desktop" for mime in TEXT_TYPES})


def read_ini(path):
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    if path.exists():
        parser.read_string(path.read_text(encoding="utf-8"))
    return parser


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Keep one pre-migration copy. Only the user's own files are touched.
    backup = path.with_name(path.name + ".pre-9.26.2")
    if path.exists() and not backup.exists():
        shutil.copy2(path, backup)
    fd, name = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def save_ini(path, parser):
    stream = io.StringIO()
    parser.write(stream, space_around_delimiters=False)
    atomic_write(path, stream.getvalue())


def remove_v1_mime_overrides(path, parser, inherited):
    backup = path.with_name(path.name + ".pre-9.26.1")
    if not backup.exists() or not parser.has_section("Default Applications"):
        return False
    previous = read_ini(backup)
    previous_defaults = previous["Default Applications"] if previous.has_section("Default Applications") else {}
    defaults = parser["Default Applications"]
    changed = False
    for mime, fallback in FALLBACKS.items():
        inherited_choice = inherited.get(mime, "").split(";", 1)[0]
        if (defaults.get(mime, "").split(";", 1)[0] == fallback
                and not previous_defaults.get(mime)
                and inherited_choice
                and inherited_choice != fallback):
            defaults.pop(mime, None)
            changed = True
    return changed


def migrate_mime(path, inherited=None, repair_v1=False):
    inherited = inherited or {}
    parser = read_ini(path)
    if not parser.has_section("Default Applications"):
        parser.add_section("Default Applications")
    defaults = parser["Default Applications"]
    changed = remove_v1_mime_overrides(path, parser, inherited) if repair_v1 else False
    for mime in IMAGE_TYPES:
        current = defaults.get(mime, "").split(";", 1)[0]
        effective = current or inherited.get(mime, "").split(";", 1)[0]
        if not effective or effective in BROWSERS:
            defaults[mime] = "eom.desktop"
            changed = True
    for mime in TEXT_TYPES:
        if not defaults.get(mime) and not inherited.get(mime):
            defaults[mime] = "pluma.desktop"
            changed = True
    if changed:
        save_ini(path, parser)


def migrate_compiz(path):
    if not path.exists():
        return
    parser = read_ini(path)
    changed = False
    for section in ("decoration", "screenshot", "commands"):
        if not parser.has_section(section):
            parser.add_section(section)
    if parser["decoration"].get("as_command", "") in (
        "", "gtk-window-decorator", "gtk-window-decorator --replace",
        "/usr/bin/gtk-window-decorator --replace",
    ):
        parser["decoration"]["as_command"] = "spaced-window-decorator"
        changed = True
    if parser["screenshot"].get("as_initiate_button", "") in ("", "<Super>Button1"):
        parser["screenshot"]["as_initiate_button"] = "<Control><Shift>Button1"
        changed = True
    # Use a vacant command slot and leave any user-assigned Shift+Print alone.
    bound = any(value in ("<Shift>Print", "<Shift>PrintScreen")
                for section in parser.sections() for value in parser[section].values())
    if not bound:
        for slot in range(12):
            command, key = f"as_command{slot}", f"as_run_command{slot}_key"
            if parser["commands"].get(command, "") or parser["commands"].get(key, ""):
                continue
            parser["commands"][command] = "mate-screenshot --area"
            parser["commands"][key] = "<Shift>Print"
            changed = True
            break
    if changed:
        save_ini(path, parser)


def migrate(config):
    state = config / "spaced"
    state.mkdir(parents=True, exist_ok=True)
    with (state / "desktop-migration.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        marker = state / "desktop-migration-9.26.2-v1"
        if marker.exists():
            return
        generic_mime = config / "mimeapps.list"
        migrate_mime(generic_mime)
        generic = read_ini(generic_mime)
        inherited = generic["Default Applications"] if generic.has_section("Default Applications") else {}
        # Desktop-specific files take precedence over mimeapps.list in MATE.
        mate_mime = config / "mate-mimeapps.list"
        if mate_mime.exists():
            migrate_mime(mate_mime, inherited, repair_v1=True)
        migrate_compiz(config / "compiz/compizconfig/Default.ini")
        btop = config / "btop/btop.conf"
        if not btop.exists():
            atomic_write(btop, 'graph_symbol = "block"\n')
        atomic_write(marker, "9.26.2\n")


if __name__ == "__main__":
    try:
        migrate(Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")))
    except (OSError, configparser.Error, UnicodeError) as error:
        print(f"Spaced desktop migration will retry at next login: {error}", file=sys.stderr)
        sys.exit(1)
