#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
OUTPUT="${LOCAL_PACKAGE_OUTPUT:-$ROOT/build/local-packages}"
VERSION="$(cat "$ROOT/VERSION")"
# Use the package revision date, so later documentation/test commits cannot
# change the bytes of an already-published native package.
export SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH:-$(git -C "$ROOT" log -1 --format=%ct -- packages/spaced-meta/DEBIAN/control packages/spaced-mate-default-settings/DEBIAN/control)}

mkdir -p "$OUTPUT"

build() {
    local pkg="$1" dir="${2:-$ROOT/packages/$1}"
    local control="$dir/DEBIAN/control"
    # Use the version from debrelease/VERSION unless the control file pins one.
    local ver="$VERSION"
    if grep -q '^Version:' "$control"; then
        ver="$(awk -F': ' '/^Version:/{print $2; exit}' "$control")"
    fi
    local out="$OUTPUT/${pkg}_${ver}_all.deb"
    # prepare copies every .deb in this directory into live-build. Remove only
    # stale versions of the package being rebuilt so an old release cannot be
    # staged beside the current one after an incremental build.
    find "$OUTPUT" -maxdepth 1 -type f -name "${pkg}_*_all.deb" \
        ! -name "${pkg}_${ver}_all.deb" -delete
    rm -f "$out"
    dpkg-deb --root-owner-group --build "$dir" "$out"
    dpkg-deb --info "$out" | sed -n '1,12p'
    echo "    -> $out"
}

stage_desktop_defaults() {
    local stage
    stage=$(mktemp -d)
    cp -a "$ROOT/packages/spaced-mate-default-settings/." "$stage/"

    # Only Spaced-owned paths belong in the update package. Package-owned
    # LightDM, MATE Media, GRUB, and Calamares files remain image-build policy
    # and are migrated narrowly from postinst where necessary.
    local path
    for path in \
        boot/grub/themes/spaced \
        etc/X11/Xsession.d/05spaced-reset-session-env \
        etc/X11/Xsession.d/25spaced-flatpak-exports \
        etc/X11/xorg.conf.d/20-spaced-amdgpu.conf \
        etc/apt/apt.conf.d \
        etc/apt/preferences.d \
        etc/apt/sources.list.d/spaced-apt.list \
        etc/bazaar \
        etc/default/spaced-first-boot-snapshot \
        etc/fastfetch \
        etc/init.d/spaced-first-boot-snapshot \
        etc/lightdm/lightdm.conf.d/60-spaced-installed.conf \
        etc/profile.d/spaced-application-theming.sh \
        etc/profile.d/spaced-flatpak-exports.sh \
        etc/profile.d/spaced-xdg-runtime.sh \
        etc/profile.d/spaced-xdg-user-dirs.sh \
        etc/skel \
        etc/brave/policies/managed/spaced-extensions.json \
        etc/xdg/autostart/spaced-audio-restore.desktop \
        etc/xdg/autostart/spaced-desktop-icon-repair-before-caja.desktop \
        etc/xdg/autostart/spaced-desktop-icon-repair.desktop \
        etc/xdg/autostart/spaced-display-repair.desktop \
        etc/xdg/autostart/spaced-enable-flatpak-remotes.desktop \
        etc/xdg/autostart/spaced-first-login-repair.desktop \
        etc/xdg/autostart/spaced-nvidia-postboot.desktop \
        etc/xdg/autostart/spaced-theme-monitor.desktop \
        etc/xdg/QtProject/qtquickcontrols2.conf \
        usr/lib/spaced-linux \
        usr/local/bin \
        usr/local/sbin \
        usr/local/share/applications/mate-about.desktop \
        usr/local/share/applications/spaced-help.desktop \
        usr/share/applications/mimeapps.list \
        usr/share/applications/spaced-nvidia-installer.desktop \
        usr/share/applications/spaced-update.desktop \
        usr/share/applications/spaced-window-manager.desktop \
        usr/share/backgrounds/spaced \
        usr/share/fastfetch/logos/spaced-linux.txt \
        usr/share/flatpak/remotes.d/flathub.flatpakrepo \
        usr/share/glib-2.0/schemas/90_spaced-linux.gschema.override \
        usr/share/glib-2.0/schemas/org.gnome.metacity.gschema.xml \
        usr/share/icons \
        usr/share/keyrings/spaced-archive-keyring.gpg \
        usr/share/mate-background-properties/spaced-linux.xml \
        usr/share/mate-panel/layouts \
        usr/share/pixmaps \
        usr/share/polkit-1/actions/com.spacedlinux.nvidia.policy \
        usr/share/polkit-1/actions/com.spacedlinux.update.policy \
        usr/share/spaced-themes
    do
        (cd "$ROOT/overlays" && cp -a --parents "$path" "$stage")
    done

    # These entrypoints are removed by Calamares. An update must not put the
    # live installer back on an installed system or in a new user's Desktop.
    rm -f "$stage/usr/local/bin/install-spaced-linux" \
        "$stage/usr/local/bin/spaced-live-session" \
        "$stage/etc/skel/Desktop/install-spaced-linux.desktop" \
        "$stage/usr/share/spaced-themes/cairo-dock/launchers/04-install.desktop"

    for path in "$ROOT"/overlays/usr/share/themes/Spaced-*; do
        (cd "$ROOT/overlays" && cp -a --parents "${path#"$ROOT/overlays/"}" "$stage")
    done

    # The signed first-party Flatpak descriptor is fetched and verified before
    # packaging. Keeping it in the settings package lets installed systems get
    # the same stable remote definition through normal APT updates.
    local external_stage=${SPACED_EXTERNAL_STAGE_DIR:-$ROOT/build/external-artifacts}
    local github_remote="$external_stage/spaced-github.flatpakrepo"
    if [[ ! -f $github_remote ]]; then
        echo "Missing verified spaced-github descriptor; run stage-external-artifacts.sh first" >&2
        exit 1
    fi
    install -Dm0644 "$github_remote" \
        "$stage/usr/share/flatpak/remotes.d/spaced-github.flatpakrepo"

    # Brisk asks the active icon theme for start-here-symbolic. Put the exact
    # issue-provided raster mark directly in each selectable theme so its
    # compiled cache cannot fall through to an old Papirus or Adwaita icon.
    for icon_theme in "$stage"/usr/share/icons/Spaced-Icons-*; do
        [ -d "$icon_theme" ] || continue
        case $(sed -n 's/^Inherits=\(Spaced-Menu-On-[^,]*\).*/\1/p' "$icon_theme/index.theme") in
            Spaced-Menu-On-Dark) menu_theme=Spaced-Menu-On-Dark ;;
            Spaced-Menu-On-Light) menu_theme=Spaced-Menu-On-Light ;;
            *) echo "Cannot determine Brisk icon surface for $icon_theme" >&2; exit 1 ;;
        esac
        if ! grep -q '^\[48x48/places\]$' "$icon_theme/index.theme"; then
        sed -i 's|^Directories=|Directories=48x48/places,|' "$icon_theme/index.theme"
        cat >> "$icon_theme/index.theme" <<'ICON_DIRECTORY'

[48x48/places]
Size=48
Context=Places
Type=Fixed
ICON_DIRECTORY
        fi
        install -d "$icon_theme/48x48/places"
        install -m 0644 \
            "$stage/usr/share/icons/$menu_theme/48x48/places/start-here.png" \
            "$stage/usr/share/icons/$menu_theme/48x48/places/start-here-symbolic.png" \
            "$icon_theme/48x48/places/"
    done

    # Do not let a developer checkout's umask leak group-writable modes into
    # an installed system.
    find "$stage" -type d -exec chmod 0755 {} +
    find "$stage" -type f -perm /111 -exec chmod 0755 {} +
    find "$stage" -type f ! -perm /111 -exec chmod 0644 {} +

    build spaced-mate-default-settings "$stage"
    rm -rf -- "$stage"
}

stage_meta() {
    local stage
    stage=$(mktemp -d)
    cp -a "$ROOT/packages/spaced-meta/." "$stage/"
    # The same runtime package groups feed both the ISO and upgrades. A new
    # driver, firmware, desktop tool or kernel must not be fresh-install-only.
    python3 - "$ROOT" "$stage/DEBIAN/control" <<'PY'
import re
import sys
from pathlib import Path
import yaml

root, control = map(Path, sys.argv[1:])
groups = yaml.safe_load((root / 'config/packages.yaml').read_text())
runtime = {package for group, packages in groups.items()
           if group not in {'installer', 'live'} for package in packages}
runtime.update({'linux-image-amd64', 'linux-headers-amd64', 'sysvinit-core',
                'devuan-keyring', 'mate-session-manager'})
text = control.read_text()
original = re.search(r'^Depends: (.+)$', text, re.M).group(1)
existing = {item.strip().split()[0] for item in original.split(',')}
depends = original + ', ' + ', '.join(sorted(runtime - existing))
control.write_text(re.sub(r'^Depends: .+$', 'Depends: ' + depends, text, flags=re.M))
PY
    build spaced-meta "$stage"
    rm -rf -- "$stage"
}

stage_desktop_defaults
stage_meta
"$ROOT/scripts/iso/stage-amdgpu-top.sh"
"$ROOT/scripts/iso/stage-marco.sh"
