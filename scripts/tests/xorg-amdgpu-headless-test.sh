#!/bin/bash
# Start a second, headless X server on an AMD GPU with the amdgpu driver and
# TearFree, draw on it, and report whether it survives (issue #298).
# It shares the running desktop's console (-sharevts, no VT switch) and
# takes no input devices, so the desktop in use is not disturbed.
#
#   sudo xorg-amdgpu-headless-test.sh [XSERVER_DEB_OR_DIR]
#
# Without an argument the installed server is tested. With a
# xserver-xorg-core .deb (or a directory it was extracted to) that server
# is tested instead, without installing it. Exit 0: the server survived;
# 1: it failed or crashed; 3: another X server holds the GPU (stop LightDM
# from a text console first).
set -uo pipefail
[ "$(id -u)" -eq 0 ] || { echo 'Run with sudo: the X server needs root to open the GPU.' >&2; exit 2; }

work=$(mktemp -d)
trap 'kill "$server" 2>/dev/null; rm -rf "$work"' EXIT
display=:${SPACED_TEST_DISPLAY:-57}

root=
if [ -n "${1:-}" ]; then
    if [ -d "$1" ]; then root=$1; else root=$work/server; dpkg-deb -x "$1" "$root"; fi
fi
xorg=${root:-}/usr/lib/xorg/Xorg
modules=/usr/lib/xorg/modules
[ -z "$root" ] || modules="$root/usr/lib/xorg/modules,$modules"
[ -x "$xorg" ] || { echo "No X server at $xorg" >&2; exit 2; }

# First PCI device bound to the amdgpu kernel driver.
busid=
for device in /sys/bus/pci/drivers/amdgpu/0000:*; do
    [ -e "$device" ] || continue
    IFS=':.' read -r _ bus dev fn <<< "${device##*/}"
    busid="PCI:$((16#$bus)):$((16#$dev)):$((16#$fn))"
    break
done
[ -n "$busid" ] || { echo 'No GPU uses the amdgpu kernel driver.' >&2; exit 2; }
vt=$(fgconsole 2>/dev/null || echo 1)

cat > "$work/xorg.conf" <<EOF
Section "ServerFlags"
    Option "AutoAddDevices" "false"
    Option "AutoEnableDevices" "false"
    Option "DontVTSwitch" "true"
EndSection
Section "Device"
    Identifier "amd"
    Driver "amdgpu"
    BusID "$busid"
    Option "TearFree" "true"
EndSection
Section "Screen"
    Identifier "screen"
    Device "amd"
EndSection
Section "ServerLayout"
    Identifier "layout"
    Screen "screen"
EndSection
EOF

log=$work/Xorg.log
echo "Testing $xorg ($(dpkg-deb -f "${1:-/dev/null}" Version 2>/dev/null || dpkg-query -W -f='${Version}' xserver-xorg-core)) on $busid"
mkdir "$work/conf.d"
"$xorg" "$display" -config "$work/xorg.conf" -configdir "$work/conf.d" -modulepath "$modules" \
    -isolateDevice "$busid" -sharevts -novtswitch "vt$vt" -nolisten tcp -noreset \
    -logfile "$log" >/dev/null 2>&1 &
server=$!

for _ in $(seq 50); do
    DISPLAY=$display xdpyinfo >/dev/null 2>&1 && break
    kill -0 "$server" 2>/dev/null || break
    sleep 0.2
done
started=no
DISPLAY=$display xdpyinfo >/dev/null 2>&1 && started=yes

if [ "$started" = yes ]; then
    # Damage is what reaches the TearFree code that crashed.
    DISPLAY=$display timeout 8 xclock -update 1 >/dev/null 2>&1 &
    DISPLAY=$display timeout 8 glxgears >/dev/null 2>&1 &
    sleep 9
fi

alive=no
kill -0 "$server" 2>/dev/null && alive=yes
grep -E 'TearFree|Segmentation|Backtrace|amdgpu_drv\.so|\(EE\)' "$log" | grep -v 'not implemented\|warning, (EE) error' | head -15
if [ "$started" = yes ] && [ "$alive" = yes ] && ! grep -q 'Segmentation fault' "$log"; then
    echo "PASS: the X server ran the amdgpu driver with TearFree and survived drawing"
    exit 0
fi
if grep -q 'is not DRM master' "$log"; then
    echo "NOT RUN: another X server holds the AMD GPU. From a text console (Ctrl+Alt+F2):"
    echo "  sudo /etc/init.d/lightdm stop; sudo $0 ${1:-}; sudo /etc/init.d/lightdm start"
    exit 3
fi
echo "FAIL: started=$started alive=$alive (log copy: /tmp/xorg-amdgpu-headless.log)"
cp "$log" /tmp/xorg-amdgpu-headless.log
exit 1
