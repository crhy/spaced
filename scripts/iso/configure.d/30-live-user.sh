#!/bin/bash
set -euo pipefail

for group in autologin bluetooth lpadmin netdev scanner; do
    getent group "$group" >/dev/null || groupadd --system "$group"
done

id -u user >/dev/null 2>&1 || useradd -m -s /bin/bash user
echo "user:1" | chpasswd
echo "root:spaced" | chpasswd
usermod -aG sudo,audio,video,plugdev,netdev,sambashare user
# Existing issue #297 policy; intentionally unchanged in this revision.
chmod 0711 /home/user
printf 'user ALL=(ALL:ALL) NOPASSWD: ALL\n' > /etc/sudoers.d/spaced-live
chmod 0440 /etc/sudoers.d/spaced-live

cp -a /etc/skel/. /home/user/
find /home/user/Desktop -maxdepth 1 -type f ! -name install-spaced-linux.desktop -delete
cat > "/home/user/Desktop/Live session passwords.txt" <<'LIVE_PASSWORDS'
Spaced Linux live session: passwords and rescue tools
Live user "user", password: 1
Root account "root", password: spaced
sudo needs no password in the live session.
These passwords exist only on this live USB; an installed system uses the
passwords chosen in the installer and locks the root account.
Rescue tools are included: GParted, TestDisk, ddrescue, smartctl.
LIVE_PASSWORDS
chown -R user:user /home/user
