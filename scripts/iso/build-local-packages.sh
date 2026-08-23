#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
OUTPUT="${LOCAL_PACKAGE_OUTPUT:-$ROOT/build/local-packages}"
VERSION="$(cat "$ROOT/VERSION")"

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
        etc/X11/Xsession.d/05spaced-reset-session-env \
        etc/X11/Xsession.d/25spaced-flatpak-exports \
        etc/apt/sources.list.d/spaced-apt.list \
        etc/bazaar \
        etc/fastfetch \
        etc/lightdm/lightdm.conf.d/60-spaced-installed.conf \
        etc/profile.d/spaced-application-theming.sh \
        etc/profile.d/spaced-flatpak-exports.sh \
        etc/profile.d/spaced-xdg-runtime.sh \
        etc/profile.d/spaced-xdg-user-dirs.sh \
        etc/skel \
        etc/xdg/autostart/spaced-audio-restore.desktop \
        etc/xdg/autostart/spaced-display-repair.desktop \
        etc/xdg/autostart/spaced-enable-flathub.desktop \
        etc/xdg/autostart/spaced-first-login-repair.desktop \
        etc/xdg/autostart/spaced-nvidia-postboot.desktop \
        etc/xdg/autostart/spaced-theme-monitor.desktop \
        etc/xdg/autostart/spaced-welcome.desktop \
        etc/xdg/QtProject/qtquickcontrols2.conf \
        usr/lib/spaced-linux \
        usr/local/bin \
        usr/share/applications/mimeapps.list \
        usr/share/applications/spaced-nvidia-installer.desktop \
        usr/share/applications/spaced-update.desktop \
        usr/share/applications/spaced-welcome.desktop \
        usr/share/applications/spaced-window-manager.desktop \
        usr/share/backgrounds/spaced \
        usr/share/fastfetch/logos/spaced-linux.txt \
        usr/share/flatpak/remotes.d/flathub.flatpakrepo \
        usr/share/glib-2.0/schemas/90_spaced-linux.gschema.override \
        usr/share/glib-2.0/schemas/org.gnome.metacity.gschema.xml \
        usr/share/icons \
        usr/share/mate-background-properties/spaced-linux.xml \
        usr/share/mate-panel/layouts \
        usr/share/pixmaps \
        usr/share/polkit-1/actions/com.spacedlinux.nvidia.policy \
        usr/share/polkit-1/actions/com.spacedlinux.update.policy \
        usr/share/spaced-themes \
        usr/share/spaced-welcome
    do
        (cd "$ROOT/overlays" && cp -a --parents "$path" "$stage")
    done

    for path in "$ROOT"/overlays/usr/share/themes/Spaced-*; do
        (cd "$ROOT/overlays" && cp -a --parents "${path#"$ROOT/overlays/"}" "$stage")
    done

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
        sed -i 's|^Directories=|Directories=48x48/places,|' "$icon_theme/index.theme"
        cat >> "$icon_theme/index.theme" <<'ICON_DIRECTORY'

[48x48/places]
Size=48
Context=Places
Type=Fixed
ICON_DIRECTORY
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

stage_desktop_defaults
build spaced-meta
