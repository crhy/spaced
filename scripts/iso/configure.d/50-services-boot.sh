#!/bin/bash
set -euo pipefail

/usr/local/sbin/spaced-sync-time || true
[ ! -e /etc/init.d/chrony ] || update-rc.d chrony defaults
[ ! -e /etc/init.d/avahi-daemon ] || update-rc.d avahi-daemon defaults
[ ! -x /usr/lib/spaced-linux/spaced-configure-printing ] || \
    /usr/lib/spaced-linux/spaced-configure-printing
[ ! -e /etc/init.d/smbd ] || update-rc.d smbd defaults
[ ! -e /etc/init.d/spaced-wsdd ] || update-rc.d spaced-wsdd defaults

# Retain smartctl while disabling the desktop-unnecessary background scanner.
update-rc.d smartmontools disable 2>/dev/null || true
[ ! -e /etc/init.d/spaced-first-boot-snapshot ] || \
    update-rc.d spaced-first-boot-snapshot defaults 98

if [ -f /etc/default/grub ]; then
    sed -i 's/^#\?GRUB_DISABLE_OS_PROBER=.*/GRUB_DISABLE_OS_PROBER=false/' /etc/default/grub
    grep -q '^GRUB_DISABLE_OS_PROBER=' /etc/default/grub || \
        echo 'GRUB_DISABLE_OS_PROBER=false' >> /etc/default/grub
fi

if [ -f /etc/init.d/ssh ]; then
    update-rc.d ssh enable 2>/dev/null || true
    mkdir -p /etc/ssh/sshd_config.d
    printf 'PasswordAuthentication yes\nPermitRootLogin yes\n' > \
        /etc/ssh/sshd_config.d/10-spaced.conf
fi
