#!/bin/bash
set -euo pipefail

rm -rf /etc/skel/.config/cairo-dock
if [ -d /usr/share/cairo-dock/themes/Default-Single ]; then
    mkdir -p /etc/skel/.config/cairo-dock/current_theme
    cp -a /usr/share/cairo-dock/themes/Default-Single/. \
        /etc/skel/.config/cairo-dock/current_theme/
    rm -rf /etc/skel/.config/cairo-dock/current_theme/launchers
    mkdir -p /etc/skel/.config/cairo-dock/current_theme/launchers
    cp -a /usr/share/spaced-themes/cairo-dock/launchers/. \
        /etc/skel/.config/cairo-dock/current_theme/launchers/
    sed -i -e 's/^modules=.*/modules=/' \
        -e 's/^visibility=.*/visibility=0/' \
        /etc/skel/.config/cairo-dock/current_theme/cairo-dock.conf
    touch /etc/skel/.config/cairo-dock/current_theme/.spaced-launchers-v1
fi

rm -f /usr/share/applications/calamares-install-debian.desktop \
    /usr/share/applications/calamares.desktop.orig \
    /usr/share/pixmaps/install-debian.png \
    /etc/xdg/autostart/calamares-desktop-icon.desktop \
    /usr/bin/add-calamares-desktop-icon \
    /usr/bin/calamares-install-debian
rm -rf /etc/calamares/branding/debian

for icon_theme in /usr/share/icons/Spaced-*; do
    [ -d "$icon_theme" ] || continue
    gtk-update-icon-cache -f "$icon_theme" >/dev/null 2>&1 || true
done

rm -f /etc/X11/xorg.conf /etc/X11/xorg.conf.d/*nvidia*.conf 2>/dev/null || true
rm -f /etc/modprobe.d/nvidia-installer-disable-nouveau.conf 2>/dev/null || true
