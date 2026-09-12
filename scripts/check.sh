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
    libfuse2t64 \
    dbus-x11 \
    elogind \
    libelogind-compat \
    libpam-elogind \
    dconf-gsettings-backend \
    mate-media \
    polkitd \
    pkexec \
    chrony \
    btop \
    gparted \
    nvtop \
    pulseaudio-utils \
    tzdata \
    firmware-nvidia-graphics \
    xserver-xorg-video-nouveau \
    wmctrl
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
import hashlib
import json
import re
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
def exact_field_values(text, key, quoted=False):
    prefix = f'{key}="' if quoted else f"{key}="
    suffix = '"' if quoted else ''
    return [line[len(prefix):-len(suffix) if suffix else None]
            for line in text.splitlines()
            if line.startswith(prefix) and line.endswith(suffix)]


def has_exact_field(text, key, value, quoted=False):
    return exact_field_values(text, key, quoted) == [value]


assert has_exact_field(os_release, "VERSION", version, quoted=True), \
    "os-release VERSION does not match VERSION"
assert has_exact_field(os_release, "VERSION_CODENAME", release_code, quoted=True), \
    "os-release codename does not match VERSION"
assert has_exact_field(lsb_release, "DISTRIB_ID", "SpacedLinux"), \
    "lsb-release distributor identity does not match the overlay"
assert has_exact_field(lsb_release, "DISTRIB_RELEASE", version), \
    "lsb-release release does not match VERSION"
assert has_exact_field(lsb_release, "DISTRIB_CODENAME", release_code), \
    "lsb-release codename does not match VERSION"
assert not has_exact_field(f"DISTRIB_RELEASE={version}.0", "DISTRIB_RELEASE", version), \
    "release field matcher accepts a non-exact release"
branding = Path("overlays/etc/calamares/branding/spaced/branding.desc").read_text(encoding="utf-8")
def calamares_field_values(key):
    return re.findall(rf"^\s+{key}:\s*(\S+)\s*$", branding, re.MULTILINE)


assert calamares_field_values("version") == [version], \
    "Calamares version does not match VERSION"
assert calamares_field_values("shortVersion") == [version], \
    "Calamares shortVersion does not match VERSION"
assert calamares_field_values("version") != [f"{version}0"], \
    "Calamares version matcher accepts a non-exact release"
for path in (
    "README.md",
    "live-build/auto/config",
    "overlays/etc/calamares/branding/spaced/branding.desc",
    "overlays/etc/calamares/branding/spaced/slideshow/Show.qml",
    "live-build/config/bootloaders/grub-pc/grub.cfg",
    "live-build/config/bootloaders/grub-pc/live-theme/theme.txt",
):
    assert f"Spaced Linux {version}" in Path(path).read_text(encoding="utf-8"), \
        f"{path} does not identify the current release"

# The website can announce a testing line while linking the last published
# image. Do not require an unpublished ISO URL merely to match VERSION.
assert version in Path("website/index.html").read_text(encoding="utf-8"), \
    "website/index.html does not identify the current development line"
for path in ("website/index.html", "website/themes.html", "website/help.html"):
    website_page = Path(path).read_text(encoding="utf-8")
    assert "https://github.com/crhy/spaced/releases" in website_page, \
        f"{path} does not link to published releases"

package_groups = loaded_yaml["config/packages.yaml"]
packages = [package for group in package_groups.values() for package in group]
duplicates = sorted(package for package, count in Counter(packages).items() if count > 1)
assert not duplicates, f"duplicate packages in config/packages.yaml: {duplicates}"
forbidden_packages = {
    "cairo-dock", "cairo-dock-plug-ins", "feh", "imagemagick",
    "firmware-linux", "firmware-linux-nonfree",
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
application_theming = Path("overlays/etc/profile.d/spaced-application-theming.sh").read_text(encoding="utf-8")
assert "QT_QPA_PLATFORMTHEME=gtk3" in application_theming \
    and "QT_STYLE_OVERRIDE=Fusion" in application_theming, \
    "Qt applications do not have a complete cross-toolkit control style (issue #78)"
assert {"bluez", "bluez-tools"}.issubset(packages), "Bluetooth stack is not included by default (issue #77)"
assert {"btop", "caja-admin", "gigolo", "gparted", "nvtop", "timeshift", "zstd"}.issubset(packages), \
    "administrator, partitioning, Windows-share, or backup desktop integration is missing"
assert "libfuse2t64" in packages, "legacy AppImages cannot start without FUSE 2 compatibility (issue #153)"
assert {"gnome-keyring", "libcanberra-gtk3-module", "accountsservice"}.issubset(packages), \
    "Flatpak/keyring or LightDM desktop integration is incomplete"
assert "mate-power-manager" in packages, \
    "MATE Power Management Control Center panel is not included (issue #98)"
defaults_control = (Path("packages/spaced-mate-default-settings/DEBIAN/control")
                    .read_text(encoding="utf-8"))
for package in ("accountsservice", "caja-admin", "gigolo", "gnome-keyring",
                "libcanberra-gtk3-module", "pulseaudio-utils", "timeshift",
                "tzdata", "wmctrl", "x11-xserver-utils",
                "xdg-desktop-portal-gtk"):
    assert package in defaults_control, \
        f"installed-system desktop updates do not depend on {package}"
defaults_postinst = (Path("packages/spaced-mate-default-settings/DEBIAN/postinst")
                     .read_text(encoding="utf-8"))
assert "autologin-user=user" in defaults_postinst and "glib-compile-schemas" in defaults_postinst, \
    "desktop package does not migrate LightDM or compile updated settings"
assert "update-desktop-database -q /usr/local/share/applications" in defaults_postinst, \
    "the higher-priority Spaced application override database is not refreshed"
local_package_builder = Path("scripts/iso/build-local-packages.sh").read_text(encoding="utf-8")
assert "stage_desktop_defaults" in local_package_builder and "usr/share/themes" in local_package_builder, \
    "spaced-mate-default-settings remains an empty metadata package"
assert "spaced-audio-restore.desktop" in local_package_builder \
    and "spaced-display-repair.desktop" in local_package_builder, \
    "installed-system update package omits audio or display recovery autostarts"
assert "spaced-first-boot-snapshot" in local_package_builder \
    and "usr/local/share/applications/mate-about.desktop" in local_package_builder, \
    "installed-system update package omits snapshot or system-info integration"
assert '-name "${pkg}_*_all.deb"' in local_package_builder and "-delete" in local_package_builder, \
    "local package builds can leave stale release versions in ISO staging"

live_build_config = Path("live-build/auto/config").read_text(encoding="utf-8")
assert "--firmware-chroot false" in live_build_config, "broad live-build firmware injection is enabled"
assert "docs/BOOTING.md" in Path("README.md").read_text(encoding="utf-8"), \
    "boot documentation reference regressed in README.md"
package_config = Path("config/packages.yaml").read_text(encoding="utf-8")
calamares_settings = Path("overlays/etc/calamares/settings.conf").read_text(encoding="utf-8")
iso_configure_hook = Path("scripts/iso/01-configure.chroot").read_text(encoding="utf-8")
assert "plymouth" not in package_config and "plymouthcfg" not in calamares_settings \
    and "plymouth-set-default-theme" not in iso_configure_hook, \
    "the fast boot path still carries the unused Plymouth stack (issue #156)"
assert not Path("live-build/config/includes.chroot/usr/share/plymouth").exists(), \
    "obsolete Plymouth artwork remains in the ISO source tree"
mirror_urls = [line.split(chr(34))[1] for line in live_build_config.splitlines() if "--mirror-" in line or "--parent-mirror-" in line]
assert len(mirror_urls) == 6 and len(set(mirror_urls)) == 1 and mirror_urls[0].endswith("/merged") and mirror_urls[0] != "http://deb.devuan.org/merged", "build mirrors must use one fixed Devuan /merged endpoint"

# Real-hardware boot must never depend on the QEMU/KVM virtual display name
# (video=Virtual-1) or a forced early GPU modeset; both freeze boot on real
# machines, and the previous occurrence regressed the 8.26 ISO (blinking cursor
# at top-left, no framebuffer). The serial-console parameter that caused the
# same symptom before it is forbidden too.
live_grub_cfg = Path("live-build/config/bootloaders/grub-pc/grub.cfg").read_text(encoding="utf-8")
assert "video=" not in live_grub_cfg and "Virtual-1" not in live_grub_cfg, \
    "live GRUB still passes the QEMU-only video=Virtual-1 display, freezing real hardware"
assert "console=ttyS0" not in live_grub_cfg and "ttyS0" not in live_build_config, \
    "serial console must not be re-added to the live kernel command line"
assert "nouveau.modeset=1" not in live_grub_cfg and "nouveau.modeset=1" not in live_build_config, \
    "forced early nouveau modeset must not return to the default boot path"
assert "--bootappend-live" in live_build_config \
    and "boot=live components quiet loglevel=3 vt.global_cursor_default=0" in live_build_config \
    and " splash " not in live_build_config, \
    "default live boot append line regressed"
assert "dhcpcd-base,ifupdown" in live_build_config, \
    "debootstrap can configure ifupdown before its non-systemd sysusers provider"
assert "live-media-timeout=" not in live_build_config + live_grub_cfg, \
    "live-media-timeout suppresses scanning and can force an initramfs failure"
qemu_common = Path("scripts/vm/qemu/common.sh").read_text(encoding="utf-8")
assert "-rtc base=utc" in qemu_common and "-rtc base=localtime" not in qemu_common, \
    "QEMU must expose a UTC hardware clock to the Linux guest"
qemu_smoke = Path("scripts/vm/qemu/smoke-iso.sh").read_text(encoding="utf-8")
assert "SPACED_QEMU_ACCEL" in qemu_smoke and "tcg,thread=multi" in qemu_smoke, \
    "headless ISO smoke testing has no non-KVM fallback"
monthly_workflow = Path(".github/workflows/monthly-iso.yml").read_text(encoding="utf-8")
assert 'cron: "23 9 1 * *"' in monthly_workflow and "make release" in monthly_workflow \
    and "make iso-smoke-kvm" in monthly_workflow and "upload-artifact@v4" in monthly_workflow, \
    "monthly ISO build, desktop boot, or evidence retention is not automated (issue #148)"
assert "live-build_20250814_all.deb" in monthly_workflow \
    and "a4bffb8e6436ffba260f2e1c37be9dd04a4dacf52c38d7bbe454ec826ba52a4b" in monthly_workflow \
    and "dpkg-query" in monthly_workflow, \
    "monthly builds do not pin the current compatible live-build toolchain"
assert "2147483648" in monthly_workflow and "GitHub release assets must be under 2 GiB" in monthly_workflow, \
    "monthly builds can publish an ISO that GitHub cannot distribute"

# The VM GPU must stay a single stable card. Layering virtio-gpu/virtio-vga on
# top of QEMU's default VGA exposes two DRM cards to the guest, stalling Xorg
# and leaving LightDM on a black screen (blinking cursor) in every test VM.
makefile_text = Path("Makefile").read_text(encoding="utf-8")
assert "plymouth/themes" not in makefile_text, \
    "the ISO build still stages the removed Plymouth theme"
assert "qemu-system-x86 qemu-utils" in makefile_text, \
    "make deps omits qemu-img, which the reusable VM scripts require"
assert "Discarding unsafe live-build bootstrap cache" in makefile_text, \
    "Makefile must reject cached bootstrap trees with unsafe core ownership"
assert '"$(abspath $(LOCAL_PACKAGE_DIR))"' in makefile_text.split("clean:", 1)[1].split("cache-clean:", 1)[0] \
    and "$(ROOT_RUN) rm -rf" in makefile_text.split("clean:", 1)[1].split("cache-clean:", 1)[0], \
    "make clean cannot remove root-owned local package artifacts"
assert "sha256sum $(ISO_NAME) > $(ISO_NAME).sha256" in makefile_text, \
    "release checksum must use the downloadable ISO basename"
assert 'chown -R 0:0 "$(abspath $(LB_DIR)/config/includes.chroot)"' in makefile_text, \
    "live-build overlay staging can preserve non-root ownership in /usr"
assert '$(HOST_RUN) scripts/build-apt-repo.sh "$(abspath $(APT_REPO_DIR))"' in makefile_text, \
    "APT repository builds do not use the host packaging tools"
assert '$(HOST_RUN) scripts/tests/test-release-package-payload.sh "$(abspath $(APT_REPO_DIR))"' in makefile_text, \
    "APT repository publication can bypass package payload validation"
assert '$(HOST_RUN) scripts/tests/test-apt-trust.sh "$(abspath $(APT_REPO_DIR))"' in makefile_text, \
    "APT repository publication can bypass signed candidate validation"
for gpu_source in (qemu_common, qemu_smoke, makefile_text):
    assert "virtio-gpu-pci" not in gpu_source and "virtio-vga" not in gpu_source, \
        "test VM must use a single GPU; dual virtio VGA leaves the guest on a black screen"
    assert "-vga std" in gpu_source, "test VM must expose exactly one VGA (QEMU standard VGA)"

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
generated_python = list(root.rglob("__pycache__")) + list(root.rglob("*.py[co]"))
assert not generated_python, f"generated Python bytecode would leak into the image: {generated_python}"

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
        "metacity-1/metacity-theme-3.xml",
    ):
        assert (directory / relative).is_file(), f"{name}: missing {relative}"
    for metacity_version in (1, 3):
        metacity_path = directory / f"metacity-1/metacity-theme-{metacity_version}.xml"
        ElementTree.parse(metacity_path)
        metacity = metacity_path.read_text(encoding="utf-8")
        assert '<distance name="title_vertical_pad" value="6"/>' in metacity, \
            f"{name} v{metacity_version}: normal titlebar click target is too small"
        assert '<distance name="title_vertical_pad" value="4"/>' in metacity, \
            f"{name} v{metacity_version}: utility titlebar click target is too small"
        assert '<distance name="button_width" value="24"/>' in metacity \
            and '<distance name="button_height" value="24"/>' in metacity, \
            f"{name} v{metacity_version}: normal titlebar buttons lack the 24px hitbox"
        assert '<distance name="button_width" value="22"/>' in metacity \
            and '<distance name="button_height" value="22"/>' in metacity, \
            f"{name} v{metacity_version}: utility titlebar buttons lack the 22px hitbox"
        assert '<aspect_ratio name="button"' not in metacity, \
            f"{name} v{metacity_version}: Marco rejects aspect ratio with explicit button dimensions"
        assert 'width="width" height="19"' not in metacity, \
            f"{name} v{metacity_version}: titlebar gradient does not cover the enlarged hit target"

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
    assert 'url("/usr/share/themes/' not in gtk3, \
        f"{name}: absolute theme imports break relocation (flatpak and unpacked themes)"
    gtk2 = (directory / "gtk-2.0/gtkrc").read_text(encoding="utf-8")
    assert "gtkrc-shared" in gtk2 and "Raleigh" not in gtk2, f"{name}: GTK2 falls back to another theme"
    assert isinstance(theme.get("dark"), bool), f"{name}: dark-mode preference is missing"

launcher = root / "etc/skel/Desktop/install-spaced-linux.desktop"
assert launcher.stat().st_mode & 0o111, "Calamares desktop launcher is not executable"
assert "Name=Install Spaced Linux" in launcher.read_text(encoding="utf-8")

build_hook = Path("scripts/iso/01-configure.chroot").read_text(encoding="utf-8")
package_builder = Path("scripts/iso/build-local-packages.sh").read_text(encoding="utf-8")
stage_script = Path("scripts/iso/stage-external-artifacts.sh").read_text(encoding="utf-8")
assert "flathub.org" not in build_hook, "image build must not depend on live Flathub access"
assert "for remote in flathub spaced-github" in build_hook \
    and 'remote-add --system --if-not-exists "$remote" "$descriptor"' in build_hook, \
    "the live image does not register both signed system Flatpak remotes"
assert "flatpak install --system" not in build_hook \
    and "SpacedBazaar.version" not in stage_script \
    and "SPACED_BAZAAR" not in stage_script, \
    "the lean ISO still embeds SpacedBazaar or another optional Flatpak payload"
assert "only after Calamares has completed" in build_hook, \
    "the image does not document its post-install application-delivery boundary"
assert "data.replace(old, new)" not in build_hook and "patch_immediate" not in build_hook, \
    "upstream binaries must be fixed with versioned source packages, never opaque byte edits"
assert "etc/xdg/QtProject/qtquickcontrols2.conf" in package_builder, \
    "update package omits the Calamares Qt Quick styling"
assert 'Spaced-Dark ] && continue' not in package_builder, \
    "update package omits the shared GTK engine used by every Spaced theme"
assert "Spaced-Icons-*" in package_builder and "start-here-symbolic.png" in package_builder, \
    "active icon-theme caches do not receive the issue-provided Brisk mark"

embedded_welcome_paths = (
    root / "usr/lib/spaced-linux/spaced-welcome.py",
    root / "usr/share/applications/spaced-welcome.desktop",
    root / "etc/xdg/autostart/spaced-welcome.desktop",
    root / "usr/local/bin/spaced-welcome",
    root / "usr/local/bin/spaced-install-apps",
    root / "usr/local/bin/spaced-github-release-asset",
    root / "usr/share/spaced-welcome/FlatpaksToInstallAfterInstall.txt",
)
assert not [path for path in embedded_welcome_paths if path.exists()], \
    "the standalone Welcome implementation is still duplicated in the distro overlay"
meta_control = Path("packages/spaced-meta/DEBIAN/control").read_text(encoding="utf-8")
package_version = re.search(r"^Version: (.+)$", meta_control, re.M).group(1)
assert package_version.split("-", 1)[0] == version, "Native package version does not match OS release"
assert f"Version: {package_version}\n" in defaults_control
assert f"spaced-mate-default-settings (= {package_version})" in meta_control \
    and "spaced-welcome (>= 0.1.14)" in meta_control \
    and "libfuse2t64" in meta_control, \
    "spaced-meta does not pull in the standalone Welcome package and desktop defaults"
assert "spaced-welcome.desktop" not in package_builder \
    and "usr/share/spaced-welcome" not in package_builder, \
    "spaced-mate-default-settings still stages standalone Welcome-owned paths"

artifact_config = Path("config/external-artifacts.conf").read_text(encoding="utf-8")
artifact_stager_path = Path("scripts/iso/stage-external-artifacts.sh")
artifact_stager = artifact_stager_path.read_text(encoding="utf-8")

def artifact_default(name):
    match = re.search(rf"\$\{{{re.escape(name)}:=([^}}]+)\}}", artifact_config)
    assert match, f"external artifact configuration is missing {name}"
    return match.group(1)

assert artifact_default("SPACED_WELCOME_REPOSITORY") == "crhy/spacedwelcome"
assert artifact_default("SPACED_WELCOME_VERSION") == "0.1.14"
assert artifact_default("SPACED_GITHUB_REMOTE_NAME") == "spaced-github"
assert artifact_default("SPACED_GITHUB_REMOTE_DESCRIPTOR_URL") == \
    "https://crhy.github.io/spacedbazaar/spaced-github.flatpakrepo"
assert artifact_default("SPACED_GITHUB_REPO_URL") == \
    "https://crhy.github.io/spacedbazaar/flatpak-repo/"
for checksum_name in (
    "SPACED_WELCOME_SHA256",
    "SPACED_GITHUB_REMOTE_SHA256",
):
    value = artifact_default(checksum_name)
    assert value == "UNRELEASED" or re.fullmatch(r"[0-9a-fA-F]{64}", value), \
        f"{checksum_name} is neither a release gate nor a SHA-256 pin"
fingerprint = artifact_default("SPACED_GITHUB_GPG_FINGERPRINT")
assert fingerprint == "UNRELEASED" or re.fullmatch(r"[0-9a-fA-F]{40}", fingerprint), \
    "spaced-github key is neither release-gated nor fingerprint-pinned"
for override in ("SPACED_WELCOME_DEB", "SPACED_GITHUB_REMOTE_FILE"):
    assert override in artifact_stager, f"verified local override is missing: {override}"
assert "amd64|x86_64" in artifact_stager and "arm64|aarch64" in artifact_stager, \
    "external artifact staging does not map supported Debian architectures"
assert "--retry 3 --retry-all-errors --connect-timeout 15" in artifact_stager \
    and "--proto '=https' --proto-redir '=https'" in artifact_stager, \
    "external artifact downloads are not HTTPS-only and retry-safe"
assert "dpkg-deb -f" in artifact_stager and "verify_sha256" in artifact_stager \
    and "SPACED_GITHUB_GPG_FINGERPRINT" in artifact_stager, \
    "external Debian or remote inputs are not fully verified"
assert makefile_text.index("scripts/iso/stage-external-artifacts.sh") < \
    makefile_text.index("scripts/iso/build-local-packages.sh", makefile_text.index("prepare:")), \
    "standalone release artifacts are not staged before local packages"
release_preflight = Path("scripts/release-preflight.sh").read_text(encoding="utf-8")
assert "release-preflight: check" in makefile_text \
    and "release: release-preflight" in makefile_text \
    and "$(MAKE) clean" in makefile_text[makefile_text.index("release: release-preflight"):], \
    "release builds do not run the fail-fast validation gate"
for release_pin in (
    "SPACED_WELCOME_SHA256",
    "SPACED_GITHUB_REMOTE_SHA256",
    "SPACED_GITHUB_GPG_FINGERPRINT",
):
    assert f"require_digest {release_pin}" in release_preflight, \
        f"release preflight does not enforce {release_pin}"
assert "SPACED_EXTERNAL_STAGE_DIR" in package_builder \
    and 'spaced-github.flatpakrepo' in package_builder, \
    "the verified spaced-github descriptor is not owned by the desktop package"
apt_repo_builder = Path("scripts/build-apt-repo.sh").read_text(encoding="utf-8")
assert apt_repo_builder.index("stage-external-artifacts.sh") < \
    apt_repo_builder.index("build-local-packages.sh") \
    and 'for package in "$package_work/packages"/*.deb' in apt_repo_builder, \
    "the APT repository omits the verified standalone Welcome dependency"

flatpak_wrapper_path = root / "usr/local/bin/flatpak"
flatpak_wrapper = flatpak_wrapper_path.read_text(encoding="utf-8")
bazaar_main = yaml.safe_load((root / "etc/bazaar/bazaar.yaml").read_text(encoding="utf-8"))
bazaar_content = yaml.safe_load((root / "etc/bazaar/config.yaml").read_text(encoding="utf-8"))
assert bazaar_main["start-on-curated"] is True \
    and "/run/host/etc/bazaar/config.yaml" in bazaar_main["curated-config-paths"], \
    "SpacedBazaar does not load the Spaced Linux catalog"
bazaar_apps = bazaar_content["rows"][0]["section"]["appids"]["list"]
assert {"io.github.crhy.SpacedBazaar", "io.github.crhy.voice2textai",
        "io.github.crhy.CardsWithCats", "io.github.crhy.BrutalChess",
        "io.github.crhy.SpacedWelcome"}.issubset(bazaar_apps), \
    "SpacedBazaar's CRHY catalog is incomplete"
# Spaced Update is part of the operating system and its menu entry runs the
# native copy. Featuring the Flatpak here invited a second, separately
# versioned install that exported an identically named launcher.
assert "org.spacedlinux.SpacedUpdate" not in bazaar_apps, \
    "Spaced Update ships with the OS and must not be offered as a Flatpak to install"
suggested_apps = {
    app_id
    for row in bazaar_content["rows"][1:]
    for app_id in row["section"]["appids"]["list"]
}
assert {"org.kde.kdenlive", "org.gimp.GIMP", "org.ardour.Ardour",
        "org.tenacityaudio.Tenacity", "org.DolphinEmu.dolphin-emu",
        "org.mozilla.thunderbird", "com.obsproject.Studio",
        "com.vscodium.codium", "com.valvesoftware.Steam"}.issubset(suggested_apps), \
    "SpacedBazaar's task-oriented suggestions are incomplete"
assert {"python3-gi", "gir1.2-gtk-3.0"}.issubset(packages), \
    "first-run GTK application dependencies are missing"
assert flatpak_wrapper_path.stat().st_mode & 0o111, "Flatpak HTTPS-bundle wrapper is not executable"
assert "https://*.flatpak" in flatpak_wrapper and "--proto-redir '=https'" in flatpak_wrapper, \
    "Flatpak HTTPS-bundle compatibility handling is missing"
assert 'real_flatpak=${SPACED_FLATPAK_REAL:-/usr/bin/flatpak}' in flatpak_wrapper, \
    "Flatpak compatibility wrapper does not delegate to the packaged binary"
assert "ensure_remote" in flatpak_wrapper and "flathub|spaced-github" in flatpak_wrapper \
    and 'remote-add --user --if-not-exists "$name" "$descriptor"' in flatpak_wrapper, \
    "terminal Flatpak installs do not self-register the signed application remotes"
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
remote_helper_path = root / "usr/local/bin/spaced-enable-flatpak-remotes"
remote_helper = remote_helper_path.read_text(encoding="utf-8")
assert remote_helper_path.stat().st_mode & 0o111, "Flatpak remote helper is not executable"
assert 'elapsed" -lt 180' in remote_helper and "sleep \"$delay\"" in remote_helper \
    and "for name in flathub spaced-github" in remote_helper, \
    "login-time signed remote registration does not survive delayed networking"
assert 'delay=$((delay * 2))' in remote_helper, \
    "offline logins still poll for Flatpak remotes at a fixed interval"
session_reset = (root / "etc/X11/Xsession.d/05spaced-reset-session-env").read_text(encoding="utf-8")
assert "AT_SPI_BUS_ADDRESS" in session_reset and "var/lib/lightdm" in session_reset \
    and "xprop -root -remove AT_SPI_BUS" in session_reset, \
    "installed sessions retain LightDM's inaccessible accessibility bus"
lightdm_config = (root / "etc/lightdm/lightdm.conf").read_text(encoding="utf-8")
assert "session-setup-script=/usr/local/sbin/spaced-lightdm-session-setup" in lightdm_config, \
    "LightDM does not clean up greeter helpers before starting the user session"
assert "autologin-user=" not in lightdm_config and "greeter-hide-users=false" in lightdm_config, \
    "installed LightDM either retains the live user or hides the remembered user list"
installed_lightdm = (root / "etc/lightdm/lightdm.conf.d/60-spaced-installed.conf").read_text(encoding="utf-8")
assert "greeter-hide-users=false" in installed_lightdm, \
    "desktop update package lacks the installed-system LightDM user-list policy"
live_configure = Path("scripts/iso/01-configure.chroot").read_text(encoding="utf-8")
assert "[LightDM]\n" in live_configure and "[LightDM]\n# Reuse Plymouth" in live_configure \
    and "minimum-vt=1\n\n[Seat:*]" in live_configure, \
    "live LightDM may deadlock waiting for an inactive VT in headless KVM"
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
for unsafe_live_setting in ("spaced-live", "49-spaced-live-gparted.rules",
                            "spaced-live-session.desktop", "50-spaced.conf",
                            "10-spaced.conf", "passwd -l root"):
    assert unsafe_live_setting in cleanup, f"Calamares does not clean up {unsafe_live_setting}"
assert "first-boot-snapshot/pending" in cleanup, \
    "Calamares does not arm the Fresh install restore point for the installed target"
calamares_packages = yaml.safe_load((root / "etc/calamares/modules/packages.conf").read_text(encoding="utf-8"))
removed_after_install = set(calamares_packages["operations"][0]["remove"])
assert {"calamares", "calamares-settings-debian", "openssh-server", "live-config-sysvinit", "squashfs-tools"}.issubset(removed_after_install), \
    "installed system retains live-only packages"
assert "/usr/local/bin/install-spaced-linux" in cleanup \
    and "/home/*/Desktop/install-spaced-linux.desktop" in cleanup \
    and "/usr/share/spaced-themes/cairo-dock/launchers/04-install.desktop" in cleanup \
    and "/home/*/.config/cairo-dock/current_theme/launchers/04-install.desktop" in cleanup, \
    "installed system retains the Spaced Linux installer launcher"
reboot_helper = root / "usr/local/bin/spaced-reboot-after-install"
assert reboot_helper.stat().st_mode & 0o111 \
    and "Remove the installation USB drive" in reboot_helper.read_text(encoding="utf-8") \
    and "zenity --question" in reboot_helper.read_text(encoding="utf-8"), \
    "post-install reboot does not warn before the USB installer is removed (issue #192)"
assert "test ! -x /usr/bin/calamares" in cleanup, \
    "Calamares cleanup lacks a hard package-removal postcondition"
assert not {"live-config-systemd", "live-task-localisation", "live-task-recommended"}.intersection(removed_after_install), \
    "Calamares package cleanup still names packages unavailable in Ceres"
assert {"locales", "console-setup"}.issubset(packages), \
    "Calamares locale or keyboard support is incomplete"
assert {"util-linux-extra", "grub-pc-bin", "grub-efi-amd64-bin", "efibootmgr", "dosfstools"}.issubset(packages), \
    "Calamares offline BIOS/UEFI install dependencies are incomplete"
assert "os-prober" in packages, "GRUB cannot detect other operating systems without os-prober"
assert "util-linux" in packages, "the testing-channel bootstrap must find runuser from util-linux"
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
assert "Open SpacedBazaar after installation to explore the full catalog" in slideshow, \
    "Calamares slideshow does not explain the application catalog"
branding = (root / "etc/calamares/branding/spaced/branding.desc").read_text(encoding="utf-8")
assert branding.count("spaced-logo.png") == 3, \
    "Calamares internal branding does not use the transparent Spaced logo"
assert "SpacedIconb" not in branding, \
    "Calamares internal branding still uses the tiled icon with a background"
fancy_icon = Path("branding/spaced-icon-fancy.png").read_bytes()
calamares_icon = root / "etc/calamares/branding/spaced/spaced-logo.png"
assert hashlib.sha256(calamares_icon.read_bytes()).digest() == hashlib.sha256(fancy_icon).digest(), \
    "Calamares does not use the fancy Spaced icon"
calamares_stylesheet = (root / "etc/calamares/branding/spaced/stylesheet.qss").read_text(encoding="utf-8")
assert "QLabel#logoApp" in calamares_stylesheet and "#1b1b1f" in calamares_stylesheet, \
    "Calamares logo transparency does not reveal the matching sidebar surface"
assert "QWidget {\n    background-color: #1b1b1f;" in calamares_stylesheet, \
    "Calamares base surface does not match the transparent logo field"
assert "Icon=install-spaced-linux" in launcher.read_text(encoding="utf-8"), \
    "Calamares desktop launcher does not use the light download-arrow icon"
installer_icon = (root / "usr/share/icons/hicolor/scalable/apps/install-spaced-linux.svg").read_text(encoding="utf-8")
assert 'width="128"' in installer_icon and 'height="128"' in installer_icon \
    and "<circle" in installer_icon, \
    "live installer icon is not large and noticeable (issue #191)"
live_hook = Path("scripts/iso/01-configure.chroot").read_text(encoding="utf-8")
assert "find /home/user/Desktop -maxdepth 1 -type f ! -name install-spaced-linux.desktop -delete" in live_hook, \
    "live desktop is not restricted to the installer icon (issue #191)"
network_server_icon = (root / "usr/share/icons/hicolor/scalable/places/network-server.svg").read_text(encoding="utf-8")
assert "#6b7078" in network_server_icon and "#b9" not in network_server_icon.lower(), \
    "Network Servers still falls back to the purple theme icon (issue #190)"
calamares_launcher = (root / "usr/local/bin/install-spaced-linux").read_text(encoding="utf-8")
assert "sudo --preserve-env=DISPLAY,XAUTHORITY,DBUS_SESSION_BUS_ADDRESS" in calamares_launcher, \
    "Calamares launcher does not use the authorized live-session sudo path"
assert "pkexec calamares" not in calamares_launcher, "Calamares launcher still uses broken pkexec authorization"
assert all(setting in calamares_launcher for setting in (
    "QT_QUICK_BACKEND=software", "QSG_RHI_BACKEND=software", "LIBGL_ALWAYS_SOFTWARE=1")), \
    "Calamares does not force its VirtualBox-safe Qt software rendering path"
assert "/tmp/calamares-root-" in calamares_launcher \
    and "umount --recursive" in calamares_launcher \
    and "swapoff --all" in calamares_launcher, \
    "failed Calamares target state prevents whole-disk retry"
calamares_locale = yaml.safe_load((root / "etc/calamares/modules/locale.conf").read_text(encoding="utf-8"))
assert calamares_locale["region"] == "America" and calamares_locale["zone"] == "Los_Angeles", \
    "Calamares does not initially select Los Angeles"

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
engine_gtk = (theme_root / "Spaced-Dark/gtk-3.0/gtk.css").read_text(encoding="utf-8")
painted_layout = {line.strip().rstrip(",") for line in engine_gtk.splitlines()} & {
    "box", "grid", "paned", "fixed", "layout", "alignment",
    "eventbox", "aspectframe", "revealer", "overlay",
}
assert not painted_layout, \
    f"GTK catch-all still paints pure layout containers: {sorted(painted_layout)}"
layout_containers = {
    "box", "grid", "paned", "fixed", "layout", "alignment",
    "eventbox", "aspectframe", "revealer", "overlay",
}
for catch_all_name in ("Spaced-Dark", "Spaced-Linux-Dark", "Spaced-Linux-Light"):
    catch_all = (theme_root / catch_all_name / "gtk-3.0/gtk.css").read_text(encoding="utf-8")
    painted = {line.strip().rstrip(",") for line in catch_all.splitlines()} & layout_containers
    assert not painted, f"{catch_all_name} catch-all still paints layout containers: {sorted(painted)}"
assert ".caja-desktop-window" in shared_gtk, "GTK CSS does not preserve Caja's wallpaper paint layer"
widget_gtk = (theme_root / "Spaced-Dark/gtk-3.0/gtk-widgets.css").read_text(encoding="utf-8")
assert "background-color: alpha(@theme_selected_bg_color, 0.18)" in widget_gtk \
    and "background-image: none" in widget_gtk \
    and "window.caja-desktop-window rubberband" in widget_gtk, \
    "GTK drag-selection rubber bands are not translucent (issue #101)"
assert "textview text selection" in shared_gtk and "entry selection" in shared_gtk, \
    "GTK text selection is not visibly highlighted"
assert "#PanelApplet #showdesktop-button" in shared_gtk, \
    "panel applet buttons do not inherit each theme's panel color"
assert "#PanelPlug" in shared_gtk and "NaTrayApplet" in shared_gtk, \
    "legacy NetworkManager tray plugs do not inherit the panel color"
assert "min-width: 28px" in shared_gtk and "min-height: 28px" in shared_gtk, \
    "window and dialog buttons still have a tiny click target (issues #6/#64/#65)"
assert "switch:checked" in shared_gtk and "min-width: 44px" in shared_gtk, \
    "modern GTK switches do not expose a clear on/off state"
assert ".path-bar button" in shared_gtk and "toolbar button" in shared_gtk, \
    "breadcrumb and toolbar buttons are not flattened onto the window surface"
assert "border-radius: 4px" in shared_gtk and "button.default" in shared_gtk, \
    "default buttons are not modernized with soft radius and accent outline"
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
assert "[org.mate.caja.preferences]" in schema_override and "show-hidden-files=true" in schema_override, \
    "Caja does not retain the requested hidden-file default"
assert "executable-text-activation='display'" in schema_override, \
    "Double-clicking a script does not open the text editor (issue #182)"
assert "[org.mate.caja.desktop]" in schema_override and "volumes-visible=true" in schema_override, \
    "Mounted network shares are not shown on the desktop (issue #184)"

icon_repair = root / "usr/local/bin/spaced-desktop-icon-repair"
assert icon_repair.stat().st_mode & 0o111 and "caja-icon-position" in icon_repair.read_text(encoding="utf-8"), \
    "Desktop icons stranded outside the current monitors are not repaired (issue #184)"
icon_repair_before_caja = (root / "etc/xdg/autostart/spaced-desktop-icon-repair-before-caja.desktop").read_text(encoding="utf-8")
assert "Exec=/usr/local/bin/spaced-desktop-icon-repair\n" in icon_repair_before_caja \
    and "X-MATE-Autostart-Phase=Panel" in icon_repair_before_caja, \
    "Desktop icon positions are not repaired before Caja starts (issue #184)"
icon_repair_autostart = (root / "etc/xdg/autostart/spaced-desktop-icon-repair.desktop").read_text(encoding="utf-8")
assert "spaced-desktop-icon-repair --watch" in icon_repair_autostart, \
    "Desktop icon repair does not follow monitor layout changes (issue #184)"

brave_policy = json.loads(
    (root / "etc/brave/policies/managed/spaced-extensions.json").read_text(encoding="utf-8"))
ublock = brave_policy["ExtensionSettings"]["jcokkipkhhgiakinbnnplhkdbjbgcgpe"]
assert brave_policy["ExtensionManifestV2Availability"] == 2 \
    and ublock["installation_mode"] == "normal_installed", \
    "Brave does not ship uBlock Origin under Manifest V2 support (issue #181)"
assert brave_policy["BraveP3AEnabled"] is False \
    and brave_policy["BraveStatsPingEnabled"] is False \
    and brave_policy["BraveWebDiscoveryEnabled"] is False \
    and brave_policy["BraveNewsDisabled"] is True \
    and brave_policy["BraveRewardsDisabled"] is True, \
    "Brave privacy, search, news, and rewards defaults are not disabled (issue #196)"
menu_on_dark = icon_root / "Spaced-Menu-On-Dark/scalable/places"
menu_on_light = icon_root / "Spaced-Menu-On-Light/scalable/places"
for menu_directory, color in ((menu_on_dark, "#b8bcc2"), (menu_on_light, "#202020")):
    menu_icon = (menu_directory / "start-here.svg").read_text(encoding="utf-8")
    menu_symbolic = (menu_directory / "start-here-symbolic.svg").read_text(encoding="utf-8")
    assert color in menu_icon and color in menu_symbolic, "light/dark transparent Spaced menu icons are incomplete"
    assert "<circle" in menu_icon and "<circle" in menu_symbolic, \
        "Brisk menu icon does not match the round Spaced mark"
    assert "<rect" not in menu_icon and "<rect" not in menu_symbolic, \
        "Spaced menu icon has a square background"
for surface in ("Spaced-Menu-On-Dark", "Spaced-Menu-On-Light"):
    raster_dir = icon_root / surface / "48x48/places"
    for raster_name in ("start-here.png", "start-here-symbolic.png"):
        raster = raster_dir / raster_name
        assert raster.is_file() and raster.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"), \
            f"{surface}: {raster_name} does not use the supplied raster Brisk mark"
    assert (raster_dir / "start-here.png").read_bytes() == \
        (raster_dir / "start-here-symbolic.png").read_bytes(), \
        f"{surface}: regular and symbolic Brisk marks differ"
for surface, color in (("Spaced-Menu-On-Dark", "#b8bcc2"),
                       ("Spaced-Menu-On-Light", "#202020")):
    actions = icon_root / surface / "scalable/actions"
    for icon_name in ("system-shutdown.svg", "system-shutdown-symbolic.svg",
                      "changes-allow.svg", "changes-allow-symbolic.svg"):
        icon_text = (actions / icon_name).read_text(encoding="utf-8")
        assert color in icon_text and 'viewBox="0 0 48 48"' in icon_text, \
            f"{surface}: {icon_name} is not a compact monochrome icon"
for theme in themes:
    icon_metadata = (icon_root / f"Spaced-Icons-{theme['gtk_theme'].removeprefix('Spaced-')}" / "index.theme")
    menu_variant = "Spaced-Menu-On-Dark" if theme["dark"] else "Spaced-Menu-On-Light"
    icon_metadata_text = icon_metadata.read_text(encoding="utf-8")
    assert icon_metadata.is_file() and f"Inherits={menu_variant},Papirus-Dark,hicolor" in icon_metadata_text, \
        f"{theme['name']}: scalable Papirus icons do not precede low-resolution hicolor fallbacks"
    assert "Directories=48x48/places," in icon_metadata_text \
        and "[48x48/places]" in icon_metadata_text, \
        f"{theme['name']}: the exact Brisk raster mark is missing from the active theme index"

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
theme_monitor = (root / "usr/local/bin/spaced-theme-monitor").read_text(encoding="utf-8")
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
assert "color-scheme 'prefer-dark'" in switcher and "color-scheme 'default'" in switcher, \
    "theme switching does not drive the toolkit color scheme"
assert "gtk-application-prefer-dark-theme" not in switcher \
    and "gtk-application-prefer-dark-theme" not in schema_override, \
    "theme switching uses a nonexistent GSettings key instead of the portal color scheme"
qt_quick_config = (root / "etc/xdg/QtProject/qtquickcontrols2.conf").read_text(encoding="utf-8")
assert "Style=Universal" in qt_quick_config and "Theme=Dark" in qt_quick_config \
    and "Accent=#cfd3d8" in qt_quick_config, \
    "Qt Quick slideshow scrollbar does not use a light grayscale accent"
for state_name in ("gtk-theme", "icon-theme", "window-theme", "wallpaper"):
    assert state_name in theme_monitor, f"theme monitor does not persist {state_name}"
assert theme_monitor.index("apply_for_gtk \"$LAST\"") < theme_monitor.index(
    "restore_setting org.mate.background picture-filename wallpaper"), \
    "theme monitor must restore a custom wallpaper after metatheme extras"
assert "gsettings monitor org.mate.background picture-filename" not in theme_monitor, \
    "wallpaper persistence must reuse the generic event-driven monitor"

first_login_repair = (root / "usr/local/bin/spaced-first-login-repair").read_text(encoding="utf-8")
assert "first-login-repair-v5" in first_login_repair, "first-login repair marker was not advanced"
assert "window-scaling-factor" not in first_login_repair and "xdpyinfo" not in first_login_repair, \
    "first-login repair overrides MATE's automatic or user-selected scaling"
assert "text/x-shellscript" in first_login_repair and "pluma.desktop" in first_login_repair, \
    "upgraded profiles do not receive the Pluma shell-script association"
assert "org.mate.caja.preferences show-hidden-files true" in first_login_repair, \
    "upgraded Caja profiles do not receive the hidden-file persistence migration"
for object_id in ("brisk-menu", "window-list", "notification-area",
                  "volume-control-applet", "clock", "show-desktop"):
    assert object_id in first_login_repair, f"panel migration does not repair {object_id}"

system_mimeapps = (root / "usr/share/applications/mimeapps.list").read_text(encoding="utf-8")
skel_mimeapps = (root / "etc/skel/.config/mimeapps.list").read_text(encoding="utf-8")
for mimeapps in (system_mimeapps, skel_mimeapps):
    assert "text/plain=pluma.desktop" in mimeapps \
        and "text/x-shellscript=pluma.desktop" in mimeapps, \
        "Pluma is not the default editor for text and shell scripts"

system_info_path = root / "usr/local/bin/spaced-system-info"
system_info = system_info_path.read_text(encoding="utf-8")
mate_about_path = root / "usr/local/share/applications/mate-about.desktop"
mate_about = mate_about_path.read_text(encoding="utf-8")
assert system_info_path.stat().st_mode & 0o111 \
    and "PRETTY_NAME" in system_info and "/proc/cpuinfo" in system_info \
    and "/proc/meminfo" in system_info, \
    "Spaced System Info does not report the release and basic hardware"
spaced_help = (root / "usr/local/share/applications/spaced-help.desktop").read_text(encoding="utf-8")
assert "Name=About Spaced Linux" in mate_about and "Exec=spaced-system-info" in mate_about \
    and "Icon=/usr/share/pixmaps/spaced-medallion.png" in mate_about, \
    "About Spaced Linux does not open its own dialog with the medallion (issues #160/#181)"
assert "Exec=spaced-welcome --page help" in spaced_help, \
    "Offline Welcome help lost its own launcher (issue #161)"
assert 'VERSION_ID' in system_info and 'https://spacedlinux.com/#donate' in system_info \
    and 'https://spacedlinux.com/' in system_info, \
    "About Spaced Linux does not show the release version with website and donation links (issue #181)"
assert not (root / "usr/share/applications/mate-about.desktop").exists(), \
    "Spaced System Info collides with mate-desktop instead of using the /usr/local override"

brave_profile = root / "etc/skel/.var/app/com.brave.Browser/config/BraveSoftware/Brave-Browser/Default"
brave_bookmarks = json.loads((brave_profile / "Bookmarks").read_text(encoding="utf-8"))
brave_preferences = json.loads((brave_profile / "Preferences").read_text(encoding="utf-8"))
bookmark_bar = brave_bookmarks["roots"]["bookmark_bar"]
bookmark_checksum = hashlib.md5()
def checksum_bookmark(node):
    bookmark_checksum.update(node["id"].encode("utf-8"))
    bookmark_checksum.update(node["name"].encode("utf-16-le"))
    bookmark_checksum.update(node["type"].encode("utf-8"))
    if node["type"] == "url":
        bookmark_checksum.update(node["url"].encode("utf-8"))
    else:
        for child in node["children"]:
            checksum_bookmark(child)
for permanent_root in ("bookmark_bar", "other", "synced"):
    checksum_bookmark(brave_bookmarks["roots"][permanent_root])
assert brave_bookmarks["checksum"] == bookmark_checksum.hexdigest(), \
    "Brave bookmarks do not carry a Chromium-compatible integrity checksum"
assert {"OpenAirShips.com", "SpacedLinux.com", "Devuan", "SpacedBazaar", "SpacedHelp", "Discord", "Telegram"} == \
    {bookmark["name"] for bookmark in bookmark_bar["children"]}, \
    "fresh Brave profiles do not receive the requested bookmark-bar links (issue #145)"
assert brave_preferences["bookmark_bar"]["show_on_all_tabs"] is True, \
    "Brave's seeded bookmarks are hidden by default"
assert brave_preferences["brave"]["new_tab_page"]["show_background_image"] is False, \
    "Brave background images are enabled by default (issue #196)"
assert brave_preferences["search"]["suggest_enabled"] is False, \
    "Brave search suggestions are enabled by default (issue #196)"
telegram = next(bookmark for bookmark in bookmark_bar["children"] if bookmark["name"] == "Telegram")
assert telegram["url"] == "https://web.telegram.org/", \
    "Telegram bookmark does not open Telegram Web (issue #196)"

display_repair = (root / "usr/local/bin/spaced-display-repair").read_text(encoding="utf-8")
audio_restore = (root / "usr/local/bin/spaced-audio-restore").read_text(encoding="utf-8")
assert "ActiveChanged (false," in display_repair and not re.search(r"^\s*xset\s+dpms\s+force\s+on", display_repair, re.M), \
    "display recovery does not cover screensaver wake and TV underscan"
assert "pactl subscribe" in audio_restore and "set-sink-mute" in audio_restore \
    and "set-sink-volume" in audio_restore, \
    "audio state is not restored and persisted for reappearing sinks"
finished = yaml.safe_load((root / "etc/calamares/modules/finished.conf").read_text(encoding="utf-8"))
assert finished["restartNowCommand"] == "/usr/local/bin/spaced-reboot-after-install", \
    "Calamares does not use the USB-removal warning before reboot (issue #192)"
assert (root / "usr/local/bin/reboot").read_text(encoding="utf-8").startswith("#!/bin/sh"), \
    "desktop users do not have an unqualified reboot command"
timezone_helper = (root / "usr/local/sbin/spaced-finalize-timezone").read_text(encoding="utf-8")
assert "/usr/share/zoneinfo/$timezone" in timezone_helper and "--systohc --utc" in timezone_helper, \
    "Calamares timezone finalization does not retain the selected zone with a UTC RTC"
time_sync = (root / "usr/local/sbin/spaced-sync-time").read_text(encoding="utf-8")
time_sync_config = yaml.safe_load((root / "etc/calamares/modules/shellprocess@spaced-time-sync.conf").read_text(encoding="utf-8"))
assert "timeout --signal=TERM --kill-after=2 12" in time_sync \
    and time_sync_config["timeout"] == 30 and time_sync.rstrip().endswith("exit 0"), \
    "offline NTP can still block or fail Calamares"
snapshot_worker_path = root / "usr/local/sbin/spaced-first-boot-snapshot"
snapshot_worker = snapshot_worker_path.read_text(encoding="utf-8")
snapshot_init_path = root / "etc/init.d/spaced-first-boot-snapshot"
snapshot_init = snapshot_init_path.read_text(encoding="utf-8")
assert snapshot_worker_path.stat().st_mode & 0o111 and snapshot_init_path.stat().st_mode & 0o111, \
    "first-boot snapshot worker or SysV init script is not executable"
assert 'comments "Fresh install"' in snapshot_worker and "--snapshot-device" in snapshot_worker \
    and "--rsync --yes --scripted --quiet" in snapshot_worker \
    and "/run/live/medium" in snapshot_worker and '"$STATE_DIR/pending"' in snapshot_worker \
    and "required_kib" in snapshot_worker, \
    "Fresh install snapshot is not one-shot, installed-only, or space-guarded (issue #149)"
assert "Default-Start:     2 3 4 5" in snapshot_init \
    and "start-stop-daemon" in snapshot_init \
    and "spaced-first-boot-snapshot defaults 98" in live_configure, \
    "Fresh install snapshot is not registered as a SysV service"
live_session = (root / "usr/local/bin/spaced-live-session").read_text(encoding="utf-8")
live_polkit = (root / "etc/polkit-1/rules.d/49-spaced-live-gparted.rules").read_text(encoding="utf-8")
assert "idle-activation-enabled false" in live_session and "lock-enabled false" in live_session \
    and "/etc/sudoers.d/spaced-live" in live_session, \
    "the live installer session can still lock or blank"
assert 'action.id == "org.gnome.gparted"' in live_polkit \
    and 'subject.user == "user"' in live_polkit \
    and "subject.local && subject.active" in live_polkit, \
    "GParted still requires an undiscoverable live-user password"
grub_defaults = (root / "etc/default/grub").read_text(encoding="utf-8")
grub_theme_dir = root / "boot/grub/themes/spaced"
grub_theme = (grub_theme_dir / "theme.txt").read_text(encoding="utf-8")
assert 'GRUB_THEME="/boot/grub/themes/spaced/theme.txt"' in grub_defaults \
    and (grub_theme_dir / "SimpleBackb.png").is_file() \
    and (grub_theme_dir / "spaced-icon-fancy.png").is_file(), \
    "the installed system does not use the Spaced GRUB theme"
assert 'desktop-image: "SimpleBackb.png"' in grub_theme \
    and 'file = "spaced-icon-fancy.png"' in grub_theme \
    and "/usr/share/backgrounds" not in grub_theme, \
    "the installed GRUB theme still depends on files outside its boot-readable directory"
assert (grub_theme_dir / "SimpleBackb.png").read_bytes() == (root / "usr/share/backgrounds/spaced/SimpleBackb.png").read_bytes(), \
    "GRUB carries a stale or reformatted background"
assert (grub_theme_dir / "spaced-icon-fancy.png").read_bytes() == fancy_icon, \
    "GRUB does not carry the fancy Spaced icon"
apt_source = (root / "etc/apt/sources.list.d/spaced-apt.list").read_text(encoding="utf-8")
assert "trusted=yes" not in apt_source \
    and "signed-by=/usr/share/keyrings/spaced-archive-keyring.gpg" in apt_source, \
    "Spaced APT must authenticate its own signed archive"

nvidia_postboot = (root / "usr/lib/spaced-linux/spaced-nvidia-postboot.py").read_text(encoding="utf-8")
assert 'wm_name.lower() != "compiz"' in nvidia_postboot \
    and '["pgrep", "-u", str(os.getuid()), "-x", "compiz"]' in nvidia_postboot, \
    "NVIDIA post-boot verification does not safely handle delayed wmctrl output"

update_app = (root / "usr/lib/spaced-linux/spaced-update.py").read_text(encoding="utf-8")
update_helper = (root / "usr/lib/spaced-linux/spaced-update-helper").read_text(encoding="utf-8")
assert "Technical details" in update_app and "Gtk.ComboBox" not in update_app, \
    "Spaced Update regressed to the Progress / CLI mode selector"
assert "spaced-primary-action" in update_app and "spaced-update-list" in update_app, \
    "Spaced Update theme-aware interface is incomplete"
assert "installed_after_update = read_installed_version()" in update_app and "finish_update" in update_app, \
    "Spaced Update does not refresh the installed OS version after an update"
assert 'scope in ("user", "system")' in update_app \
    and '"runtime/' in update_app and 'flatpak-update' in update_helper, \
    "Spaced Update must handle both Flatpak scopes, applications, and runtimes"
assert 'apt-refresh' in update_helper and 'flock -n' in update_helper \
    and 'APT::Update::Error-Mode=any' in update_helper, \
    "Spaced Update must serialize transactions and reject incomplete APT indexes"
assert not list(Path("overlays").rglob("spaced-upgrade-testing.sh")), \
    "the testing-channel bootstrap is a host script and must not stage into the ISO"

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
