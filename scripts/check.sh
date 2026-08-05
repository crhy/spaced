#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
CHECK_TMP=$(mktemp -d)
trap 'rm -rf "$CHECK_TMP"' EXIT

# Ensure the live-build package generator handles valid indentationless YAML
# emitted by PyYAML, rather than silently producing an empty image package list.
generated_packages=$(scripts/iso/package-list.sh)

if [[ -z "$generated_packages" ]]; then
    echo "scripts/iso/package-list.sh produced an empty package list" >&2
    exit 1
fi

for required_package in \
    libglib2.0-bin \
    dbus-x11 \
    elogind \
    libelogind-compat \
    libpam-elogind \
    dconf-gsettings-backend \
    mate-media \
    polkitd \
    pkexec \
    chrony \
    firmware-nvidia-graphics \
    xserver-xorg-video-nouveau
do
    if ! grep -Fxq "$required_package" <<<"$generated_packages"; then
        echo "Generated package list is missing: $required_package" >&2
        exit 1
    fi
done

for forbidden_package in \
    dbus-user-session \
    pavucontrol \
    systemd \
    systemd-sysv
do
    if grep -Fxq "$forbidden_package" <<<"$generated_packages"; then
        echo "Forbidden package requested: $forbidden_package" >&2
        exit 1
    fi
done

python3 - <<'PY'
import glob
import json
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree

import yaml

loaded_yaml = {}
for path in glob.glob("config/*.yaml"):
    with open(path, encoding="utf-8") as source:
        loaded_yaml[path] = yaml.safe_load(source)

version = Path("VERSION").read_text(encoding="utf-8").strip()
release_code = version.replace(".", "")
iso_config = loaded_yaml["config/iso.yaml"]
assert iso_config["version"] == version, "config/iso.yaml version does not match VERSION"
assert iso_config["iso_name"] == f"spaced-linux-{version}", \
    "config/iso.yaml ISO name does not match VERSION"
os_release = Path("overlays/etc/os-release").read_text(encoding="utf-8")
lsb_release = Path("overlays/etc/lsb-release").read_text(encoding="utf-8")
assert f'VERSION_CODENAME="{release_code}"' in os_release, \
    "os-release codename does not match VERSION"
assert f"DISTRIB_CODENAME={release_code}" in lsb_release, \
    "lsb-release codename does not match VERSION"
for path in (
    "README.md",
    "website/index.html",
    "website/themes.html",
    "live-build/auto/config",
    "overlays/etc/calamares/branding/spaced/branding.desc",
    "overlays/etc/calamares/branding/spaced/slideshow/Show.qml",
    "live-build/config/bootloaders/grub-pc/grub.cfg",
    "live-build/config/bootloaders/grub-pc/live-theme/theme.txt",
):
    assert f"Spaced Linux {version}" in Path(path).read_text(encoding="utf-8"), \
        f"{path} does not identify the current release"

package_groups = loaded_yaml["config/packages.yaml"]
packages = [package for group in package_groups.values() for package in group]
duplicates = sorted(package for package, count in Counter(packages).items() if count > 1)
assert not duplicates, f"duplicate packages in config/packages.yaml: {duplicates}"
forbidden_packages = {
    "cairo-dock", "cairo-dock-plug-ins", "feh", "imagemagick",
    "firmware-linux", "firmware-linux-nonfree", "nvtop",
    "xorriso", "xserver-xorg-video-qxl", "yad",
}
assert not forbidden_packages.intersection(packages), "obsolete runtime/build-helper package returned"
assert "xdg-utils" in packages, "Flatpak menu refresh requires xdg-desktop-menu from xdg-utils"
assert "ca-certificates" in packages, "HTTPS clients require an explicit CA trust store when recommends are disabled"
assert "libpam-elogind" in packages, "MATE shutdown requires elogind PAM session registration"
assert "libglib2.0-bin" in packages, "glib-compile-schemas is required by the image configuration hook"
assert "policykit-1" not in packages, "Devuan Ceres replaces policykit-1 with polkitd and pkexec"
assert {"polkitd", "pkexec"}.issubset(packages), "Spaced utilities require Devuan Ceres polkitd and pkexec packages"
assert "dbus-x11" in packages, "SysVinit MATE and GTK portals require the dbus-x11 alternative"
assert {"bluez", "bluez-tools"}.issubset(packages), "Bluetooth stack is not included by default (issue #77)"

live_build_config = Path("live-build/auto/config").read_text(encoding="utf-8")
assert "--firmware-chroot false" in live_build_config, "broad live-build firmware injection is enabled"
mirror_urls = [line.split(chr(34))[1] for line in live_build_config.splitlines() if "--mirror-" in line or "--parent-mirror-" in line]
assert len(mirror_urls) == 6 and len(set(mirror_urls)) == 1 and mirror_urls[0].endswith("/merged") and mirror_urls[0] != "http://deb.devuan.org/merged", "build mirrors must use one fixed Devuan /merged endpoint"
qemu_common = Path("scripts/vm/qemu/common.sh").read_text(encoding="utf-8")
assert "-rtc base=utc" in qemu_common and "-rtc base=localtime" not in qemu_common, \
    "QEMU must expose a UTC hardware clock to the Linux guest"

root = Path("overlays")
theme_root = root / "usr/share/themes"
icon_root = root / "usr/share/icons"
wallpaper_root = root / "usr/share/backgrounds/spaced"

with open(root / "etc/calamares/modules/welcome.conf", encoding="utf-8") as source:
    welcome = yaml.safe_load(source)
assert welcome["requirements"]["requiredStorage"] == 5, "Calamares storage minimum must be 5 GB"

with open(root / "usr/share/spaced-themes/themes.json", encoding="utf-8") as source:
    themes = json.load(source)["themes"]

assert len(themes) == 10, f"expected 10 supported themes, found {len(themes)}"
assert len({t['id'] for t in themes}) == len(themes), "duplicate theme id"
assert len({t['gtk_theme'] for t in themes}) == len(themes), "duplicate GTK theme mapping"

expected = {t["gtk_theme"] for t in themes}
present = {p.name for p in theme_root.glob("Spaced-*") if (p / "index.theme").is_file()}
assert present == expected, f"theme directory mismatch: expected {sorted(expected)}, found {sorted(present)}"
assert "Spaced-Dark" not in present, "internal GTK base is still exposed as a duplicate selectable theme"

private_assets = [p for p in theme_root.rglob("*") if p.is_file() and not p.stat().st_mode & 0o004]
assert not private_assets, f"theme assets are unreadable after root-owned ISO install: {private_assets}"

for theme in themes:
    name = theme["gtk_theme"]
    directory = theme_root / name
    for relative in (
        "index.theme",
        "gtk-2.0/gtkrc",
        "gtk-3.0/gtk.css",
        "gtk-3.0/index.theme",
        "metacity-1/index.theme",
        "metacity-1/metacity-theme-1.xml",
    ):
        assert (directory / relative).is_file(), f"{name}: missing {relative}"
    metacity_path = directory / "metacity-1/metacity-theme-1.xml"
    ElementTree.parse(metacity_path)
    metacity = metacity_path.read_text(encoding="utf-8")
    assert '<distance name="title_vertical_pad" value="5"/>' in metacity, \
        f"{name}: normal titlebar click target is too small"
    assert '<distance name="title_vertical_pad" value="3"/>' in metacity, \
        f"{name}: utility titlebar click target is too small"
    assert 'width="width" height="19"' not in metacity, \
        f"{name}: titlebar gradient does not cover the enlarged hit target"

    metadata = (directory / "index.theme").read_text(encoding="utf-8")
    values = {}
    for line in metadata.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    assert values.get("GtkTheme") == name, f"{name}: GtkTheme mismatch"
    assert values.get("MetacityTheme") == name, f"{name}: MetacityTheme mismatch"

    icon = values.get("IconTheme", "")
    assert (icon_root / icon / "index.theme").is_file(), f"{name}: missing icon theme {icon}"
    assert (icon_root / icon / "scalable/places/folder.svg").is_file(), f"{name}: missing folder icon"

    background = values.get("BackgroundImage", "")
    prefix = "/usr/share/backgrounds/spaced/"
    assert background.startswith(prefix), f"{name}: invalid BackgroundImage"
    assert (wallpaper_root / background.removeprefix(prefix)).is_file(), f"{name}: missing wallpaper"

    gtk3 = (directory / "gtk-3.0/gtk.css").read_text(encoding="utf-8")
    assert "spaced-overrides.css" in gtk3, f"{name}: shared GTK3 surface rules are not loaded"
    gtk2 = (directory / "gtk-2.0/gtkrc").read_text(encoding="utf-8")
    assert "gtkrc-shared" in gtk2 and "Raleigh" not in gtk2, f"{name}: GTK2 falls back to another theme"
    assert isinstance(theme.get("dark"), bool), f"{name}: dark-mode preference is missing"

launcher = root / "etc/skel/Desktop/install-spaced-linux.desktop"
assert launcher.stat().st_mode & 0o111, "Calamares desktop launcher is not executable"
assert "Name=Install Spaced Linux" in launcher.read_text(encoding="utf-8")

build_hook = Path("scripts/iso/01-configure.chroot").read_text(encoding="utf-8")
assert "flathub.org" not in build_hook, "image build must not depend on live Flathub access"
assert "flatpak remote-add --system --if-not-exists flathub" in build_hook \
    and "/usr/share/flatpak/remotes.d/flathub.flatpakrepo" in build_hook, \
    "Bazaar's sandboxed backend does not get a real system Flathub remote"
assert 'old = b"%s (as superuser)"' in build_hook and "data.replace(old, new)" in build_hook, \
    "Flatpak X11 windows retain Marco's false superuser title suffix"

welcome_app = root / "usr/lib/spaced-linux/spaced-welcome.py"
welcome_launcher = root / "usr/share/applications/spaced-welcome.desktop"
welcome_autostart = root / "etc/xdg/autostart/spaced-welcome.desktop"
welcome_wrapper = (root / "usr/local/bin/spaced-welcome").read_text(encoding="utf-8")
flatpak_installer = (root / "usr/local/bin/spaced-install-apps").read_text(encoding="utf-8")
flatpak_list = (root / "usr/share/spaced-welcome/FlatpaksToInstallAfterInstall.txt").read_text(encoding="utf-8")
flatpak_wrapper_path = root / "usr/local/bin/flatpak"
flatpak_wrapper = flatpak_wrapper_path.read_text(encoding="utf-8")
assert welcome_app.is_file() and welcome_launcher.is_file() and welcome_autostart.is_file(), \
    "Spaced Linux first-run application is incomplete"
assert "/run/live/medium" in welcome_wrapper and "welcome-shown" in welcome_wrapper, \
    "first-run application is not limited to one installed-system launch"
assert "io.github.kolunmi.Bazaar" in flatpak_installer, "Bazaar installer action is missing"
for app_id in ("org.atheme.audacious", "io.github.kolunmi.Bazaar", "com.brave.Browser",
               "org.libreoffice.LibreOffice", "org.videolan.VLC"):
    assert app_id in flatpak_list, f"suggested Flatpak is missing: {app_id}"
assert "https://github.com/crhy/Voice2Text-AI/releases/latest/download/Voice2Text-AI.flatpak" in flatpak_list, \
    "Voice2Text does not use GitHub's stable latest-release URL"
assert "/releases/download/v" not in flatpak_list, "Voice2Text is pinned to a stale release"
assert {"python3-gi", "gir1.2-gtk-3.0"}.issubset(packages), \
    "first-run GTK application dependencies are missing"
assert flatpak_wrapper_path.stat().st_mode & 0o111, "Flatpak HTTPS-bundle wrapper is not executable"
assert "https://*.flatpak" in flatpak_wrapper and "--proto-redir '=https'" in flatpak_wrapper, \
    "Flatpak HTTPS-bundle compatibility handling is missing"
assert 'real_flatpak=${SPACED_FLATPAK_REAL:-/usr/bin/flatpak}' in flatpak_wrapper, \
    "Flatpak compatibility wrapper does not delegate to the packaged binary"
assert "ensure_flathub" in flatpak_wrapper and "remote-add --user --if-not-exists flathub" in flatpak_wrapper, \
    "terminal Flatpak installs do not self-register the Flathub remote"
system_flathub = (root / "usr/share/flatpak/remotes.d/flathub.flatpakrepo").read_text(encoding="utf-8")
assert "[Flatpak Repo]" in system_flathub and "Url=https://dl.flathub.org/repo/" in system_flathub \
    and "GPGKey=" in system_flathub, \
    "Bazaar cannot enumerate the catalog without a trusted system Flathub remote"
assert "update-desktop-database" in flatpak_wrapper and "xdg-desktop-menu forceupdate" in flatpak_wrapper, \
    "Flatpak installs do not refresh the desktop application menu"
flatpak_xsession = (root / "etc/X11/Xsession.d/25spaced-flatpak-exports").read_text(encoding="utf-8")
flatpak_profile = (root / "etc/profile.d/spaced-flatpak-exports.sh").read_text(encoding="utf-8")
for environment in (flatpak_xsession, flatpak_profile):
    assert "$HOME/.local/share/flatpak/exports/share" in environment, \
        "user Flatpak exports are absent from XDG_DATA_DIRS"
    assert "/var/lib/flatpak/exports/share" in environment, \
        "system Flatpak exports are absent from XDG_DATA_DIRS"
flathub_helper = (root / "usr/local/bin/spaced-enable-flathub").read_text(encoding="utf-8")
assert "seq 1 90" in flathub_helper and "sleep 2" in flathub_helper, \
    "login-time Flathub registration does not survive delayed networking"
session_reset = (root / "etc/X11/Xsession.d/05spaced-reset-session-env").read_text(encoding="utf-8")
assert "AT_SPI_BUS_ADDRESS" in session_reset and "var/lib/lightdm" in session_reset \
    and "xprop -root -remove AT_SPI_BUS" in session_reset, \
    "installed sessions retain LightDM's inaccessible accessibility bus"
lightdm_config = (root / "etc/lightdm/lightdm.conf").read_text(encoding="utf-8")
assert "session-setup-script=/usr/local/sbin/spaced-lightdm-session-setup" in lightdm_config, \
    "LightDM does not clean up greeter helpers before starting the user session"
lightdm_setup = (root / "usr/local/sbin/spaced-lightdm-session-setup").read_text(encoding="utf-8")
assert "at-spi-bus-launcher" in lightdm_setup and "at-spi2-registryd" in lightdm_setup, \
    "LightDM session cleanup does not stop stale greeter accessibility helpers"

calamares_settings = yaml.safe_load((root / "etc/calamares/settings.conf").read_text(encoding="utf-8"))
exec_modules = next(phase["exec"] for phase in calamares_settings["sequence"] if "exec" in phase)
assert "shellprocess@spaced-cleanup" in exec_modules, "Calamares target cleanup is not scheduled"
assert "shellprocess@spaced-machineid" in exec_modules and "machineid" not in exec_modules, \
    "Calamares still depends on systemd-machine-id-setup"
assert not {"sources-media", "sources-media-unmount", "sources-final"}.intersection(exec_modules), \
    "Calamares still uses Debian media/final repository helpers"
assert "bootloader-config" not in exec_modules, \
    "Calamares still tries to download a mutually-exclusive active GRUB package"
instances = calamares_settings.get("instances", [])
assert any(instance.get("module") == "shellprocess" and instance.get("id") == "spaced-cleanup"
           for instance in instances), "Calamares cleanup module instance is not declared"
assert any(instance.get("module") == "shellprocess" and instance.get("id") == "spaced-machineid"
           for instance in instances), "Calamares sysvinit machine-ID module is not declared"
assert calamares_settings.get("hide-back-and-next-during-exec") is False, \
    "Calamares execution-navigation policy is missing"
cleanup = (root / "etc/calamares/modules/shellprocess@spaced-cleanup.conf").read_text(encoding="utf-8")
for unsafe_live_setting in ("spaced-live", "50-spaced.conf", "10-spaced.conf", "passwd -l root"):
    assert unsafe_live_setting in cleanup, f"Calamares does not clean up {unsafe_live_setting}"
calamares_packages = yaml.safe_load((root / "etc/calamares/modules/packages.conf").read_text(encoding="utf-8"))
removed_after_install = set(calamares_packages["operations"][0]["remove"])
assert {"calamares", "calamares-settings-debian", "openssh-server", "live-config-sysvinit", "squashfs-tools"}.issubset(removed_after_install), \
    "installed system retains live-only packages"
assert "/usr/local/bin/install-spaced-linux" in cleanup \
    and "/home/*/Desktop/install-spaced-linux.desktop" in cleanup \
    and "/usr/share/spaced-themes/cairo-dock/launchers/04-install.desktop" in cleanup \
    and "/home/*/.config/cairo-dock/current_theme/launchers/04-install.desktop" in cleanup, \
    "installed system retains the Spaced Linux installer launcher"
assert "test ! -x /usr/bin/calamares" in cleanup, \
    "Calamares cleanup lacks a hard package-removal postcondition"
assert not {"live-config-systemd", "live-task-localisation", "live-task-recommended"}.intersection(removed_after_install), \
    "Calamares package cleanup still names packages unavailable in Ceres"
assert {"locales", "console-setup"}.issubset(packages), \
    "Calamares locale or keyboard support is incomplete"
assert {"util-linux-extra", "grub-pc-bin", "grub-efi-amd64-bin", "efibootmgr", "dosfstools"}.issubset(packages), \
    "Calamares offline BIOS/UEFI install dependencies are incomplete"
assert "os-prober" in packages, "GRUB cannot detect other operating systems without os-prober"
default_grub = (root / "etc/default/grub").read_text(encoding="utf-8")
assert "GRUB_DISABLE_OS_PROBER=false" in default_grub and "#GRUB_DISABLE_OS_PROBER=false" not in default_grub, \
    "GRUB os-prober is still disabled, so other OSes never appear in the boot menu (issue #11)"
assert "qml6-module-qtquick-window" in packages, "Calamares slideshow QML dependency is missing"
assert "squashfs-tools" in packages, "Calamares cannot unpack the live filesystem without unsquashfs"
calamares_users = yaml.safe_load((root / "etc/calamares/modules/users.conf").read_text(encoding="utf-8"))
assert calamares_users["passwordRequirements"]["minLength"] == 1, \
    "Calamares does not permit single-character passwords"
machineid = (root / "etc/calamares/modules/shellprocess@spaced-machineid.conf").read_text(encoding="utf-8")
assert "dbus-uuidgen" in machineid and "systemd-machine-id-setup" not in machineid, \
    "Calamares machine identity generation is not sysvinit-native"
assert "ln -s /var/lib/dbus/machine-id /etc/machine-id" in machineid, \
    "Calamares does not expose the generated D-Bus machine ID"
slideshow = (root / "etc/calamares/branding/spaced/slideshow/Show.qml").read_text(encoding="utf-8")
assert slideshow.count("Slide {") == 8, "Calamares slideshow does not contain all eight showcase slides"
for screenshot in ("MacOS.png", "ModernAItools.png", "Music.png", "Spreadsheet.png",
                   "Themes.png", "Video.png", "browser.png", "wordprocess.png"):
    image = root / "etc/calamares/branding/spaced/slideshow/images" / screenshot
    assert image.is_file(), f"Calamares slideshow screenshot is missing: {screenshot}"
    assert f'source: "images/{screenshot}"' in slideshow, f"Calamares slideshow does not use {screenshot}"
assert "Open Bazaar after installation to explore the full catalog" in slideshow, \
    "Calamares slideshow does not explain the application catalog"
branding = (root / "etc/calamares/branding/spaced/branding.desc").read_text(encoding="utf-8")
assert branding.count("../../../../usr/share/backgrounds/spaced/SpacedIconb.png") == 3, \
    "Calamares internal branding does not use the detailed Spaced icon"
assert "Icon=install-spaced-linux" in launcher.read_text(encoding="utf-8"), \
    "Calamares desktop launcher does not use the light download-arrow icon"
calamares_launcher = (root / "usr/local/bin/install-spaced-linux").read_text(encoding="utf-8")
assert "sudo --preserve-env=DISPLAY,XAUTHORITY,DBUS_SESSION_BUS_ADDRESS" in calamares_launcher, \
    "Calamares launcher does not use the authorized live-session sudo path"
assert "pkexec calamares" not in calamares_launcher, "Calamares launcher still uses broken pkexec authorization"

compiz = root / "etc/skel/.config/compiz/compizconfig/Default.ini"
assert compiz.is_file(), "Compiz profile is not in the Compiz 0.8 path"
compiz_config = root / "etc/skel/.config/compiz/compizconfig/config"
assert compiz_config.is_file(), "Compiz ini backend is not configured"
compiz_text = compiz.read_text(encoding="utf-8")
assert "core;ccp;" in compiz_text, "Compiz profile does not activate ccp"
assert ";dbus;" not in compiz_text, "Compiz D-Bus plug-in crashes the Ceres live session"
assert ";wobbly;" not in compiz_text and ";animation;" not in compiz_text, \
    "distracting Compiz animations are enabled by default"
assert ";clone;" not in compiz_text and ";expo;" not in compiz_text, \
    "Clone Output or Expo is enabled by default"
assert "firepaint" in compiz_text, "Compiz paint-fire-on-screen plugin is not enabled"
assert "cube;3d;focuspoll;rotate;scale;ezoom;" in compiz_text, "Compiz desktop effects regressed"
assert "compiz-plugins-extra" in packages, "Compiz 3D Windows plug-in package is missing"
assert "as_zoom_in_key = <Shift><Super>Up" in compiz_text, "Compiz enhanced zoom shortcut regressed"
window_manager = (root / "usr/local/bin/spaced-window-manager").read_text(encoding="utf-8")
assert 'if [ "$status" -eq 0 ]' in window_manager and "xprop -root" in window_manager, \
    "normal logout is still treated as a Compiz crash"

shared_gtk = (theme_root / "Spaced-Dark/gtk-3.0/spaced-overrides.css").read_text(encoding="utf-8")
assert ".caja-desktop-window" in shared_gtk, "GTK CSS does not preserve Caja's wallpaper paint layer"
assert "#PanelApplet #showdesktop-button" in shared_gtk, \
    "panel applet buttons do not inherit each theme's panel color"
assert "#PanelPlug" in shared_gtk and "NaTrayApplet" in shared_gtk, \
    "legacy NetworkManager tray plugs do not inherit the panel color"
assert "min-width: 28px" in shared_gtk and "min-height: 28px" in shared_gtk, \
    "window and dialog buttons still have a tiny click target (issues #6/#64/#65)"
assert "switch:checked" in shared_gtk and "min-width: 44px" in shared_gtk, \
    "modern GTK switches do not expose a clear on/off state"
for glyph in ("object-select-symbolic.svg", "list-remove-symbolic.svg", "media-record-symbolic.svg"):
    glyph_path = icon_root / "hicolor/scalable/actions" / glyph
    assert glyph_path.is_file(), f"checkbox/radio glyph is missing: {glyph} (issue #78)"
mimeapps = (root / "usr/share/applications/mimeapps.list").read_text(encoding="utf-8")
assert "x-scheme-handler/http=com.brave.Browser.desktop" in mimeapps \
    and "x-scheme-handler/https=com.brave.Browser.desktop" in mimeapps \
    and "text/html=com.brave.Browser.desktop" in mimeapps, \
    "web links are not defaulted to Brave (issue #35)"
skel_mimeapps = (root / "etc/skel/.config/mimeapps.list").read_text(encoding="utf-8")
assert "x-scheme-handler/http=com.brave.Browser.desktop" in skel_mimeapps \
    and "x-scheme-handler/https=com.brave.Browser.desktop" in skel_mimeapps \
    and "text/html=com.brave.Browser.desktop" in skel_mimeapps, \
    "new user profiles do not preserve Brave as the web handler (issue #35)"
gschema = (root / "usr/share/glib-2.0/schemas/90_spaced-linux.gschema.override").read_text(encoding="utf-8")
assert "text-scaling-factor=1.2" in gschema, "HiDPI text scaling is not configured (issue #6/#64)"
wallpaper_catalog = (root / "usr/share/mate-background-properties/spaced-linux.xml").read_text(encoding="utf-8")
assert "SimpleBackb.png" in wallpaper_catalog, "GRUB background is missing from MATE wallpapers"
assert "spaced-orbit-4k.png" in wallpaper_catalog, "4K Spaced Orbit wallpaper is missing from MATE wallpapers"
orbit_wallpaper = wallpaper_root / "spaced-orbit-4k.png"
assert orbit_wallpaper.is_file() and orbit_wallpaper.read_bytes()[16:24] == bytes.fromhex("00000f0000000870"), \
    "Spaced Orbit wallpaper is not a 3840x2160 PNG"
themes_by_id = {theme["id"]: theme for theme in themes}
assert "spaced-dark" not in themes_by_id, "duplicate Spaced Dark theme is still selectable"
assert themes_by_id["win11-dark"]["panel_color"] == "#17243b", \
    "Windows 11 Dark panel is not dark blue"
assert themes_by_id["android"]["panel_color"] == "#263238", \
    "Android panel is not Material blue-gray"
assert themes_by_id["linux-dark"]["panel_color"] == "#2f2f2f", \
    "Spaced Linux Dark panel is not the darker neutral gray"
android_layout = (root / "usr/share/mate-panel/layouts/spaced-android.layout").read_text(encoding="utf-8")
assert "BriskMenuFactory::BriskMenu" in android_layout, "Android layout is missing the Brisk menu"

# Validate all themed panel layouts have consistent applet composition
panel_layouts = [p for p in (root / "usr/share/mate-panel/layouts").glob("spaced-*.layout")]
assert len(panel_layouts) >= 9, f"expected at least 9 panel layouts, found {len(panel_layouts)}"
required_applets = {"BriskMenuFactory::BriskMenu", "WnckletFactory::WindowListApplet",
                    "NotificationAreaAppletFactory::NotificationArea",
                    "GvcAppletFactory::GvcApplet", "ClockAppletFactory::ClockApplet",
                    "WnckletFactory::ShowDesktopApplet"}
for layout_path in panel_layouts:
    text = layout_path.read_text(encoding="utf-8")
    missing = required_applets - {a for a in required_applets if a in text}
    assert not missing, f"{layout_path.name}: missing applets {missing}"
    assert "locked=true" in text, f"{layout_path.name}: panel applets are not locked"

# Every theme shares the same single-panel layout; only the orientation changes.
canonical_layout = (root / "usr/share/mate-panel/layouts/spaced-linux.layout").read_text(encoding="utf-8")
for layout_path in panel_layouts:
    if layout_path.name == "spaced-linux.layout":
        continue
    text = layout_path.read_text(encoding="utf-8")
    diff = [ln for ln in text.splitlines() if ln not in canonical_layout.splitlines()]
    assert diff == [] or diff == ["orientation=top"], \
        f"{layout_path.name} diverges from the single-panel layout: {diff}"

# The panel GvcApplet is the single volume control; mate-media's tray icon must
# not autostart on top of it or every login shows two volume icons.
tray_volume_autostart = (root / "etc/xdg/autostart/mate-volume-control-status-icon.desktop")
tray_volume_text = tray_volume_autostart.read_text(encoding="utf-8")
assert "Hidden=true" in tray_volume_text, "mate-media tray volume icon still autostarts alongside the panel applet"

schema_override = (root / "usr/share/glib-2.0/schemas/90_spaced-linux.gschema.override").read_text(encoding="utf-8")
assert "format='12-hour'" in schema_override and "show-date=false" in schema_override, \
    "clock does not default to 12-hour time without the date"
menu_on_dark = icon_root / "Spaced-Menu-On-Dark/scalable/places"
menu_on_light = icon_root / "Spaced-Menu-On-Light/scalable/places"
for menu_directory, color in ((menu_on_dark, "#f3f3f3"), (menu_on_light, "#202020")):
    menu_icon = (menu_directory / "start-here.svg").read_text(encoding="utf-8")
    menu_symbolic = (menu_directory / "start-here-symbolic.svg").read_text(encoding="utf-8")
    assert color in menu_icon and color in menu_symbolic, "light/dark transparent S menu icons are incomplete"
    assert "<rect" not in menu_icon and "<rect" not in menu_symbolic, "S menu icon has a square background"
for theme in themes:
    icon_metadata = (icon_root / f"Spaced-Icons-{theme['gtk_theme'].removeprefix('Spaced-')}" / "index.theme")
    menu_variant = "Spaced-Menu-On-Dark" if theme["dark"] else "Spaced-Menu-On-Light"
    assert icon_metadata.is_file() and f"Inherits={menu_variant},hicolor,Papirus-Dark" in icon_metadata.read_text(encoding="utf-8"), \
        f"{theme['name']}: icon theme does not select the correct transparent S menu icon"

for theme_name, panel_color in (("Spaced-Win11-Dark", "#17243b"),
                                ("Spaced-Android", "#263238"),
                                ("Spaced-Linux-Dark", "#2f2f2f")):
    gtk3 = (theme_root / theme_name / "gtk-3.0/gtk.css").read_text(encoding="utf-8")
    assert f"@define-color theme_bg_color {panel_color}" in gtk3, \
        f"{theme_name}: notification/menu background does not match the panel"
    assert f"@define-color menu_bg_color {panel_color}" in gtk3, \
        f"{theme_name}: Brisk menu background does not match the panel"

win311_gtk = (theme_root / "Spaced-Win311/gtk-3.0/gtk.css").read_text(encoding="utf-8")
assert "@define-color panel_bg_color #c0c0c0" in win311_gtk, "Windows 3.11 panel is not gray"
assert all(theme["panel_size"] == 30 for theme in themes), \
    "all themes must use the Spaced Linux Dark 30 px panel size"
winxp_gtk = (theme_root / "Spaced-WinXP/gtk-3.0/gtk.css").read_text(encoding="utf-8")
assert "#PanelApplet button.brisk-button" in winxp_gtk, "Windows XP Brisk button is not themed"
assert ".brisk-menu .categories-list" in winxp_gtk, "Windows XP Brisk popup lacks Luna surfaces"
assert "notebook > stack:not(:only-child)" in winxp_gtk, "Windows XP notebook clients are not Luna colored"
geoworks_gtk = (theme_root / "Spaced-Geoworks/gtk-3.0/gtk.css").read_text(encoding="utf-8")
assert "#PanelApplet button" in geoworks_gtk, "GeoWorks applet surfaces are not themed"
winxp_folder = (icon_root / "Spaced-Icons-WinXP/scalable/places/folder.svg").read_text(encoding="utf-8")
assert "#d6b35a" in winxp_folder and "#57b65a" not in winxp_folder, "Windows XP folder is not manila"
for surface, body_color in (("Spaced-Menu-On-Dark", "#e5e7eb"),
                            ("Spaced-Menu-On-Light", "#4b5563")):
    for trash_name in ("user-trash.svg", "user-trash-full.svg"):
        trash = (icon_root / surface / "scalable/places" / trash_name).read_text(encoding="utf-8")
        assert body_color in trash and "viewBox=\"0 0 64 64\"" in trash, \
            f"{surface} {trash_name} is not a scalable high-contrast SVG"

assert not (root / "etc/skel/.config/cairo-dock/current_theme").exists(), \
    "Cairo-Dock current_theme must be built as a directory by the live hook"
assert "Default-Single" in build_hook, "Cairo-Dock default theme is not seeded"
assert "spaced-themes/cairo-dock/launchers" in build_hook, "Cairo-Dock uses stale upstream launchers"
vm_install = Path("scripts/vm/qemu/install.sh").read_text(encoding="utf-8")
assert "-boot order=c,once=d" in vm_install, "installer KVM does not boot the installed disk after reboot"

switcher = (root / "usr/local/bin/spaced-switch-theme").read_text(encoding="utf-8")
assert "background_schema" in switcher and "panel_color" in switcher, \
    "theme switcher does not apply explicit panel colors"
assert "cairo-dock -c -f" in switcher, "Cairo-Dock must use its QEMU-safe plug-in-free mode"
assert "current_theme" in switcher, "Cairo-Dock runtime config repair is missing"
assert "spaced-launchers-v1" in switcher, "Cairo-Dock launcher migration is missing"
assert "org.mate.terminal.profile:/org/mate/terminal/profiles/default/" in switcher, \
    "theme switching does not update the MATE Terminal profile"
assert "terminal_background='#000000'" in switcher and "terminal_foreground='#888888'" in switcher, \
    "dark themes do not use gray on black in MATE Terminal"
assert "terminal_background='#ffffff'" in switcher and "terminal_foreground='#000000'" in switcher, \
    "light themes do not use black on white in MATE Terminal"

first_login_repair = (root / "usr/local/bin/spaced-first-login-repair").read_text(encoding="utf-8")
assert "first-login-repair-v3" in first_login_repair, "panel migration marker was not advanced"
for object_id in ("brisk-menu", "window-list", "notification-area",
                  "volume-control-applet", "clock", "show-desktop"):
    assert object_id in first_login_repair, f"panel migration does not repair {object_id}"

update_app = (root / "usr/lib/spaced-linux/spaced-update.py").read_text(encoding="utf-8")
update_helper = (root / "usr/lib/spaced-linux/spaced-update-helper").read_text(encoding="utf-8")
assert "Technical details" in update_app and "Gtk.ComboBox" not in update_app, \
    "Spaced Update regressed to the Progress / CLI mode selector"
assert "spaced-primary-action" in update_app and "spaced-update-list" in update_app, \
    "Spaced Update theme-aware interface is incomplete"
assert 'if [ "$MODE" != "all" ]' in update_helper and "No Flatpak applications were selected" in update_helper, \
    "Spaced Update helper does not validate privileged update requests"

fastfetch_logo = (root / "usr/share/fastfetch/logos/spaced-linux.txt").read_text(encoding="utf-8")
assert "~**+<{{{{{{{{)+~~" in fastfetch_logo, "fastfetch logo is not the current Spaced ASCII art"
PY

python3 -m json.tool overlays/usr/share/spaced-themes/themes.json >/dev/null

while IFS= read -r -d '' path; do
    first_line=$(head -n 1 "$path" 2>/dev/null || true)
    case "$path:$first_line" in
        *.sh:*|*bash*) bash -n "$path" ;;
        *'/bin/sh'*) sh -n "$path" ;;
    esac
done < <(find scripts overlays packages live-build/auto -type f \
    \( -name '*.sh' -o -perm /111 -o -path '*/Xsession.d/*' \) -print0)

find overlays -type f -name '*.py' -print0 | \
    xargs -0 -r env PYTHONPYCACHEPREFIX="$CHECK_TMP/pycache" python3 -m py_compile

if find overlays live-build -type f \
    \( -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.webp' -o -iname '*.svg' \) \
    -perm /111 -print -quit | grep -q .; then
    echo "Static image assets must not be executable." >&2
    exit 1
fi

if command -v desktop-file-validate >/dev/null 2>&1; then
    # Cairo-Dock launcher files intentionally carry its legacy Container,
    # Order, and "Icon Type" keys, which are not freedesktop desktop keys.
    find overlays -name '*.desktop' -type f \
        ! -path '*/cairo-dock/launchers/*' \
        -exec desktop-file-validate {} +
fi

# Spaced Linux must use Devuan repositories exclusively.
if grep -RInE \
    'https?://([^/]*\.)?(deb\.debian\.org|security\.debian\.org|ftp\.debian\.org)' \
    live-build config overlays scripts Makefile
then
    echo "Direct Debian repository URL detected. Use Devuan /merged only." >&2
    exit 1
fi

version=$(cat VERSION)
if ! grep -q "PRETTY_NAME=\"Spaced Linux $version\"" overlays/etc/os-release; then
    echo "overlays/etc/os-release does not match VERSION ($version)" >&2
    exit 1
fi
if ! grep -q "VERSION_ID=\"$version\"" overlays/etc/os-release; then
    echo "overlays/etc/os-release VERSION_ID does not match VERSION ($version)" >&2
    exit 1
fi

echo "All source checks passed."
