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


def atomic_write(path, content, backup=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Keep one pre-migration copy. Only the user's own files are touched.
    backup_path = path.with_name(path.name + ".pre-9.26.2")
    if backup and path.exists() and not backup_path.exists():
        shutil.copy2(path, backup_path)
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


def migrate_compiz_focus(path):
    # 9.26.4 enabled a "focus" plug-in that Compiz 0.8 does not have. The real
    # control is core's focus-stealing prevention, which kept nm-applet's
    # Wi-Fi password dialog from receiving keyboard focus (issue #234).
    if not path.exists():
        return
    parser = read_ini(path)
    if not parser.has_section("core"):
        parser.add_section("core")
    changed = parser.remove_section("focus")
    plugins = parser["core"].get("as_active_plugins", "")
    if "focus" in plugins.split(";"):
        parser["core"]["as_active_plugins"] = ";".join(
            plugin for plugin in plugins.split(";") if plugin != "focus")
        changed = True
    # Keep a match the user chose; "any" is Compiz's default.
    if parser["core"].get("s0_focus_prevention_match", "any") == "any":
        parser["core"]["s0_focus_prevention_match"] = "!(class=Nm-applet)"
        changed = True
    if changed:
        save_ini(path, parser)


def migrate_firepaint(path):
    """Apply the Spaced fire-writing defaults for Compiz's firepaint plug-in (#353)."""
    if not path.exists():
        return
    parser = read_ini(path)
    if not parser.has_section("firepaint"):
        parser.add_section("firepaint")
    defaults = {
        "s0_fire_size": "3.000000",
        "s0_fire_color": "#ffffffff",
        "s0_fire_life": "0.800000",
        "s0_bg_brightness": "80",
        "s0_num_particles": "4000",
        "as_clear_button": "<Shift><Super>Button3",
    }
    changed = False
    for key, value in defaults.items():
        if key not in parser["firepaint"]:
            parser["firepaint"][key] = value
            changed = True
    if changed:
        save_ini(path, parser)


def migrate_window_previews(path):
    """Enable the stable taskbar previews supplied by Compiz Extras (#350)."""
    if not path.exists():
        return
    parser = read_ini(path)
    if not parser.has_section("core"):
        return
    serialized = parser["core"].get("as_active_plugins", "")
    plugins = serialized.split(";")
    if not serialized or "thumbnail" in plugins:
        return
    # Keep the plug-in order otherwise intact.  Window Previews has no
    # dependency on later effects, but loading it before workarounds matches
    # the new-account profile and the order CCSM itself writes.
    try:
        plugins.insert(plugins.index("workarounds"), "thumbnail")
    except ValueError:
        insert_at = len(plugins) - 1 if plugins[-1] == "" else len(plugins)
        plugins.insert(insert_at, "thumbnail")
    parser["core"]["as_active_plugins"] = ";".join(plugins)
    save_ini(path, parser)


DEFAULT_HOTKEYS = (
    ("spaced-hotkey-action voxa", "<Control><Alt>v"),
    ("spaced-hotkey-action close-window", "<Control><Alt>x"),
    ("spaced-hotkey-action mute", "<Control><Alt>m"),
    ("spaced-hotkey-action lock", "<Control><Alt>l"),
    ("spaced-hotkey-action mute-calc", "<Control><Alt>c"),
    ("spaced-hotkey-action shortcuts", "<Control><Alt>k"),
    ("spaced-hotkey-action sound", "<Control><Alt>s"),
)


def migrate_default_hotkeys(path):
    """Fill vacant command slots without taking over a user's binding (#351)."""
    if not path.exists():
        return
    parser = read_ini(path)
    if not parser.has_section("commands"):
        parser.add_section("commands")
    commands = parser["commands"]
    changed = False
    for wanted_command, wanted_key in DEFAULT_HOTKEYS:
        values = {value.lower() for section in parser.sections()
                  for value in parser[section].values()}
        # An existing key binding belongs to the user. An existing command may
        # have been moved to a different key and must not be duplicated.
        if wanted_key.lower() in values or wanted_command.lower() in values:
            continue
        for slot in range(12):
            command, key = f"as_command{slot}", f"as_run_command{slot}_key"
            if commands.get(command, "") or commands.get(key, ""):
                continue
            commands[command] = wanted_command
            commands[key] = wanted_key
            changed = True
            break
    if changed:
        save_ini(path, parser)


def migrate_spelling(config):
    """Teach Enchant-aware desktop applications the project names (#333)."""
    dictionary = config / "enchant/en_US.dic"
    try:
        existing = dictionary.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        existing = []
    words = {line.strip() for line in existing if line.strip()}
    missing = [word for word in ("Compiz", "Spaced") if word not in words]
    if missing:
        content = "\n".join(existing + missing) + "\n"
        atomic_write(dictionary, content, backup=False)


def migrate_menu_editor(path):
    """Replace the stale MenuLibre slot with the editor shipped in the image."""
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return
    updated = content.replace("<Filename>menulibre.desktop</Filename>",
                              "<Filename>alacarte.desktop</Filename>")
    if updated != content:
        atomic_write(path, updated)


def migrate(config):
    state = config / "spaced"
    state.mkdir(parents=True, exist_ok=True)
    with (state / "desktop-migration.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        focus_marker = state / "desktop-migration-10.26-v1"
        if not focus_marker.exists():
            migrate_compiz_focus(config / "compiz/compizconfig/Default.ini")
            atomic_write(focus_marker, "10.26\n")
        firepaint_marker = state / "desktop-migration-10.26-firepaint-v1"
        if not firepaint_marker.exists():
            migrate_firepaint(config / "compiz/compizconfig/Default.ini")
            atomic_write(firepaint_marker, "10.26\n")
        previews_marker = state / "desktop-migration-10.26-window-previews-v1"
        if not previews_marker.exists():
            migrate_window_previews(config / "compiz/compizconfig/Default.ini")
            atomic_write(previews_marker, "10.26.7\n")
        migrate_spelling(config)
        migrate_menu_editor(config / "menus/mate-applications.menu")
        marker = state / "desktop-migration-9.26.2-v1"
        if not marker.exists():
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
        # Run this after the old screenshot migration, so existing accounts
        # retain its slot and the new defaults fill only what remains vacant.
        hotkeys_marker = state / "desktop-migration-10.26-default-hotkeys-v1"
        if not hotkeys_marker.exists():
            migrate_default_hotkeys(config / "compiz/compizconfig/Default.ini")
            atomic_write(hotkeys_marker, "10.26.7\n")


if __name__ == "__main__":
    try:
        migrate(Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")))
    except (OSError, configparser.Error, UnicodeError) as error:
        print(f"Spaced desktop migration will retry at next login: {error}", file=sys.stderr)
        sys.exit(1)
