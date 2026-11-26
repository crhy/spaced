#!/bin/bash
set -euo pipefail

install -Dm0644 /etc/os-release /usr/lib/os-release

mkdir -p /etc/lightdm/lightdm.conf.d
cat > /etc/lightdm/lightdm.conf.d/50-spaced.conf <<'LIGHTDM'
[LightDM]
# Reuse Plymouth's active VT. Headless KVM can otherwise leave Xorg waiting
# forever for a switch from tty1 to LightDM's traditional tty7.
minimum-vt=1

[Seat:*]
autologin-user=user
autologin-user-timeout=0
greeter-session=lightdm-gtk-greeter
greeter-setup-script=/usr/local/sbin/spaced-lightdm-greeter-setup
session-setup-script=/usr/local/sbin/spaced-lightdm-session-setup
user-session=mate
LIGHTDM

# Dependencies must already be present; never hide an incomplete image by
# downloading packages from a rolling repository during this hook.
for package in spaced-mate-default-settings spaced-themes spaced-wallpapers mate-session-manager; do
    dpkg -s "$package" >/dev/null 2>&1 || {
        echo "$package was not installed" >&2
        exit 1
    }
done

glib-compile-schemas /usr/share/glib-2.0/schemas/
