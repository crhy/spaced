#!/bin/bash
# Spaced issue #413: "I chose to take over a partition and the installer said it
# would reuse [the other partition] for /home ... Following the install and
# reboot, it had not reused it for /home as stated."
#
# This test drives the REAL installer in a VM and checks the result on disk:
#   * a 20G virtio disk is prepared with a fake previous installation
#     (/dev/vda1 = "oldroot", /dev/vda2 = "oldhome" holding keep.txt files),
#   * Calamares is started exactly like the live desktop starts it and walked
#     through the pages with screenshots + OCR + xdotool (scripts/vm/qemu/gui.sh),
#     choosing "Replace a partition" and ticking "Reuse <partition> as home
#     partition for <system>",
#   * afterwards the installed /dev/vda1/etc/fstab must mount the UUID of
#     /dev/vda2 at /home, and the old home directories must still be there.
#
# On 11.26 the expected outcome is FAIL (no /home line in fstab, and the old
# /home/user directory is deleted by "userdel -r user"); 11.26.1 adds the
# spacedfstabguard module and must PASS.
set -euo pipefail

usage() {
    cat >&2 <<'USAGE'
Usage: install-reuse-home.sh ISO

Boot the live ISO headless in QEMU (KVM, BIOS, -boot order=d) with a fresh 20G
virtio disk that contains a previous Linux installation, drive Calamares over
the VM screen (QMP screenshots, tesseract OCR, xdotool over SSH) using
"Replace a partition" + "Reuse <partition> as home partition", then verify on
the installed disk that /etc/fstab mounts the reused partition at /home and
that the previous home data survived.

Environment: SPACED_V2_WALK_TRIES (installer walk retries, default 3) and
SPACED_V2_LIVE_PREP (one root command run in the live session first, only for
diagnosing the 11.26 image; see the source comment).

Exit codes: 0 = PASS, 1 = FAIL, 2 = could not run.
Artifacts: build/vm-tests/v02/<iso-name>/
USAGE
}

ISO=${1:-}
if [ -z "$ISO" ]; then
    usage
    exit 2
fi
if [ ! -f "$ISO" ]; then
    echo "ISO not found: $ISO" >&2
    exit 2
fi

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd "$SCRIPT_DIR/../../.." && pwd)
SSH_PORT=${SPACED_VM_SSH_PORT:-2232}
VNC_DISPLAY=${SPACED_QEMU_VNC_DISPLAY:-42}
RAM=${SPACED_QEMU_RAM:-4096}
CPUS=${SPACED_QEMU_CPUS:-4}
ROOT_PASSWORD=${SPACED_LIVE_ROOT_PASSWORD:-spaced}
BOOT_TIMEOUT=${SPACED_ISO_BOOT_TIMEOUT:-300}
DESKTOP_TIMEOUT=${SPACED_DESKTOP_TIMEOUT:-180}
INSTALL_TIMEOUT=${SPACED_INSTALL_TIMEOUT:-2400}
POLL=${SPACED_VM_POLL:-5}
GUI_SCALE=${SPACED_GUI_SCALE:-2}
DISK_SIZE=${SPACED_V2_DISK_SIZE:-20G}
WALK_TRIES=${SPACED_V2_WALK_TRIES:-3}
# Diagnostic hook: one shell command run as root in the live session before the
# installer starts. 11.26 has no smartmontools in its live image, and Calamares
# then segfaults when the reuse-home check box is clicked (see the task notes),
# so the 11.26 run needs SPACED_V2_LIVE_PREP='apt-get update && apt-get install
# -y --no-install-recommends smartmontools' to reach the install at all.
LIVE_PREP=${SPACED_V2_LIVE_PREP:-}
ISO_NAME=${ISO##*/}
ISO_NAME=${ISO_NAME%.iso}
OUT=${SPACED_V2_DIR:-$PROJECT_ROOT/build/vm-tests/v02/$ISO_NAME}

for value in "$SSH_PORT" "$VNC_DISPLAY" "$RAM" "$CPUS" "$BOOT_TIMEOUT" \
             "$DESKTOP_TIMEOUT" "$INSTALL_TIMEOUT" "$POLL" "$GUI_SCALE" "$WALK_TRIES"; do
    [[ "$value" =~ ^[0-9]+$ ]] || { echo "Invalid numeric VM setting: $value" >&2; exit 2; }
done
for tool in qemu-system-x86_64 qemu-img sshpass ssh python3 tesseract; do
    command -v "$tool" >/dev/null || { echo "$tool is required for the reused-home install test" >&2; exit 2; }
done
if [ ! -e /dev/kvm ]; then
    echo "This test needs KVM (/dev/kvm): a full Calamares install must run at real speed" >&2
    exit 2
fi

mkdir -p "$OUT/pages" "$OUT/screens"
OUT=$(cd "$OUT" && pwd)
PAGES="$OUT/pages"
DISK="$OUT/disk.qcow2"
QMP_SOCKET="$OUT/qmp.sock"
rm -f "$OUT/qemu.log" "$OUT/qemu-serial.log" "$OUT/qemu-img.log" "$OUT/session.log" \
    "$OUT/installed-etc-fstab" "$OUT/verify.txt" "$OUT/os-prober.txt" \
    "$OUT/session-failed.log" "$PAGES"/* "$OUT/screens"/* "$DISK"

export SPACED_VM_SSH_PORT="$SSH_PORT"
export SPACED_VM_QMP_SOCKET="$QMP_SOCKET"
export SPACED_LIVE_ROOT_PASSWORD="$ROOT_PASSWORD"
export SPACED_GUI_DIR="$OUT/screens"
export SPACED_GUI_SCALE="$GUI_SCALE"

QEMU_PID=''

# shellcheck disable=SC2329  # invoked by the EXIT trap
cleanup() {
    # QEMU is our own direct child; it is killed by that recorded PID only.
    if [ -n "$QEMU_PID" ] && kill -0 "$QEMU_PID" 2>/dev/null; then
        kill "$QEMU_PID" 2>/dev/null || true
        for _ in {1..20}; do
            kill -0 "$QEMU_PID" 2>/dev/null || break
            sleep 0.2
        done
        kill -KILL "$QEMU_PID" 2>/dev/null || true
    fi
    [ -z "$QEMU_PID" ] || wait "$QEMU_PID" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# shellcheck disable=SC1091  # gui.sh is sourced at runtime; it is checked on its own
. "$SCRIPT_DIR/gui.sh"

guest_ssh() {
    SSHPASS="$ROOT_PASSWORD" sshpass -e ssh -p "$SSH_PORT" \
        -o ConnectTimeout=10 -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null root@127.0.0.1 "$@"
}

ssh_is_ready() {
    local banner=
    if ! exec 3<>"/dev/tcp/127.0.0.1/$SSH_PORT" 2>/dev/null; then
        return 1
    fi
    IFS= read -r -t 2 banner <&3 || true
    exec 3<&-
    exec 3>&-
    [[ "$banner" == SSH-* ]]
}

wait_for_ssh() {
    local timeout=$1 started=$SECONDS
    while (( SECONDS - started < timeout )); do
        if ssh_is_ready && guest_ssh 'printf ok' >/dev/null 2>&1; then
            return 0
        fi
        if [ -n "$QEMU_PID" ] && ! kill -0 "$QEMU_PID" 2>/dev/null; then
            return 1
        fi
        sleep "$POLL"
    done
    return 1
}

# Save the current screen and its OCR text as page evidence, and echo the text.
page_capture() {
    local name=$1 png="$PAGES/$1.png" text
    gui_shot "$png" >/dev/null || true
    text=$(tesseract "$png" - --psm 11 2>/dev/null || true)
    printf '%s\n' "$text" > "$PAGES/$name.txt"
    echo "--- screen text: $name ---"
    printf '%s\n' "$text"
    echo "--- end of $name ---"
}

# Report what changed between two screenshots (used to confirm that the check
# box click changed the check box and nothing else).
screen_diff() {
    local before=$1 after=$2
    python3 -c '
import sys
from PIL import Image, ImageChops

before = Image.open(sys.argv[1]).convert("L")
after = Image.open(sys.argv[2]).convert("L")
diff = ImageChops.difference(before, after).point(lambda value: 255 if value > 40 else 0)
box = diff.getbbox()
if box is None:
    print("changed=0")
else:
    # Count on a 1/8 copy: the scale is only used for a rough pixel count.
    small = diff.resize((diff.width // 8, diff.height // 8))
    changed = sum(1 for pixel in small.getdata() if pixel)
    print("changed~{}x64 bbox_screen={},{}..{},{}".format(
        changed, box[0] // 2, box[1] // 2, box[2] // 2, box[3] // 2))
' "$before" "$after" 2>/dev/null || echo "changed=unknown"
}

click_next() {
    if gui_click "Next" 2>/dev/null; then
        return 0
    fi
    echo "  Next is not readable by OCR, pressing Alt+N"
    gui_key alt+n
}

installer_alive() {
    guest_ssh 'pgrep -x calamares >/dev/null'
}

stop_installer() {
    # shellcheck disable=SC2016  # the $() runs in the guest, not here
    guest_ssh 'for p in $(pgrep -x calamares); do kill "$p" 2>/dev/null; done; sleep 2;
               for p in $(pgrep -x calamares); do kill -KILL "$p" 2>/dev/null; done' || true
    sleep 2
}

start_installer() {
    guest_ssh "su - user -c 'DISPLAY=:0 XAUTHORITY=/home/user/.Xauthority setsid /usr/local/bin/install-spaced-linux >/dev/null 2>&1 &'" || true
}

# ---------------------------------------------------------------------------
# b. the previous installation the installer is asked to take over
# ---------------------------------------------------------------------------
prepare_old_system() {
    local marker=$1
    guest_ssh 'bash -s' <<PREPARE
set -e
for part in /dev/vda1 /dev/vda2 /dev/vda; do
    umount --recursive "\$part" 2>/dev/null || true
done
wipefs -a /dev/vda >/dev/null 2>&1 || true
parted -s /dev/vda mklabel msdos
parted -s /dev/vda mkpart primary ext4 1MiB 12GiB
parted -s /dev/vda mkpart primary ext4 12GiB 100%
partprobe /dev/vda >/dev/null 2>&1 || true
udevadm settle >/dev/null 2>&1 || true
mkfs.ext4 -F -L oldroot /dev/vda1 >/dev/null
mkfs.ext4 -F -L oldhome /dev/vda2 >/dev/null
mkdir -p /mnt/v02home
mount /dev/vda2 /mnt/v02home
mkdir -p /mnt/v02home/olduser /mnt/v02home/user
printf 'KEEP-OLDUSER-$marker\n' > /mnt/v02home/olduser/keep.txt
printf 'KEEP-USER-$marker\n' > /mnt/v02home/user/keep.txt
chown -R 1000:1000 /mnt/v02home/olduser /mnt/v02home/user
sync
umount /mnt/v02home
ROOT_UUID=\$(blkid -s UUID -o value /dev/vda1)
HOME_UUID=\$(blkid -s UUID -o value /dev/vda2)
mkdir -p /mnt/v02root
mount /dev/vda1 /mnt/v02root
mkdir -p /mnt/v02root/etc /mnt/v02root/lib64 /mnt/v02root/boot
mkdir -p /mnt/v02root/home /mnt/v02root/usr /mnt/v02root/var
cp /etc/os-release /mnt/v02root/etc/os-release
sed -i 's/^NAME=.*/NAME="Old Linux"/; s/^PRETTY_NAME=.*/PRETTY_NAME="Old Linux"/' \\
    /mnt/v02root/etc/os-release
cp /lib64/ld-linux-x86-64.so.2 /mnt/v02root/lib64/
printf 'UUID=%s / ext4 defaults 0 1\n' "\$ROOT_UUID" > /mnt/v02root/etc/fstab
printf 'UUID=%s /home ext4 defaults 0 2\n' "\$HOME_UUID" >> /mnt/v02root/etc/fstab
sync
umount /mnt/v02root
echo "HOME_UUID=\$HOME_UUID"
lsblk -o NAME,SIZE,LABEL,TYPE /dev/vda
PREPARE
}

# ---------------------------------------------------------------------------
# c/d. walk the installer pages up to (and including) the summary page
# ---------------------------------------------------------------------------
walk_to_summary() {
    if ! gui_wait "Welcome" 180; then
        page_capture welcome-timeout
        echo "The installer welcome page never appeared"
        return 1
    fi
    page_capture 1-welcome
    click_next
    page_capture 2-locale
    click_next
    page_capture 3-keyboard
    click_next

    if ! gui_wait "Replace a partition" 60; then
        page_capture 4-partition-no-replace
        echo "The partition page does not offer 'Replace a partition'"
        return 1
    fi
    gui_click "Replace a partition"
    sleep 2
    page_capture 4-partition-replace

    # Select the previous root partition. Calamares 3.4.3 draws no partition
    # names in the replace view: the "Current:" bar is the partition view, and
    # its leftmost segment is the first partition (/dev/vda1).
    local label selected=no
    for label in oldroot "/dev/vda1" ext4; do
        if gui_click "$label" 2>/dev/null; then
            selected=yes
            echo "Selected a partition by clicking its '$label' text"
            break
        fi
    done
    if [ "$selected" != yes ]; then
        page_capture 4-partition-noselection
        echo "Could not select the previous root partition in the partition view"
        return 1
    fi
    sleep 2
    if ! installer_alive; then
        page_capture 4-partition-crashed
        echo "Calamares died after selecting the partition"
        return 1
    fi
    page_capture 5-partition-selected

    if ! gui_wait "as home partition" 60; then
        page_capture 5-partition-no-reuse
        echo "The 'Reuse ... as home partition' check box never appeared"
        return 1
    fi
    local reuse_text
    reuse_text=$(tesseract "$PAGES/5-partition-selected.png" - --psm 11 2>/dev/null || true)
    if ! printf '%s\n' "$reuse_text" | grep -qi 'vda2'; then
        echo "The reuse check box does not name /dev/vda2: $(printf '%s\n' "$reuse_text" | grep -i 'home partition' || echo '(none)')"
    fi

    # Tick the check box. In manual testing most clicks on it segfaulted
    # Calamares 3.4.3 / Qt 6.11 inside libQt6Gui (see the task notes): clicks on
    # the indicator, and clicks followed by moving the pointer off the
    # installer window, always died; clicking the label text and keeping the
    # pointer inside the window survived. The script still checks that the
    # installer is alive afterwards and re-walks the pages when it is not.
    local reuse_xy reuse_x reuse_y
    reuse_xy=$(gui_find "Reuse") || { echo "The 'Reuse' label disappeared"; return 1; }
    read -r reuse_x reuse_y <<< "$reuse_xy"
    echo "Reuse label centre at $reuse_x,$reuse_y; clicking the check box label"
    gui_shot "$PAGES/6-before-tick.png" >/dev/null || true
    gui_x xdotool mousemove "$reuse_x" "$reuse_y" click 1 mousemove 900 470
    sleep 2
    gui_shot "$PAGES/6-after-tick.png" >/dev/null || true
    echo "  check box click effect: $(screen_diff "$PAGES/6-before-tick.png" "$PAGES/6-after-tick.png")"
    if ! installer_alive; then
        echo "Calamares died when the reuse check box was clicked"
        return 1
    fi

    click_next
    if ! gui_wait "your name" 60; then
        page_capture 7-users-missing
        echo "The users page did not appear"
        return 1
    fi
    page_capture 7-users

    # The first text field sits just below the "What is your name?" label; the
    # rest of the page is filled with Tab (Calamares pre-fills the login name,
    # so select-all before typing it).
    local name_xy name_x name_y
    name_xy=$(gui_find "your name") || { echo "No full name field found"; return 1; }
    read -r name_x name_y <<< "$name_xy"
    echo "Full name label at $name_x,$name_y; clicking the field at $name_x,$((name_y + 30))"
    gui_click_xy "$name_x" "$((name_y + 30))"
    sleep 1
    gui_type "Test User"
    gui_key Tab
    gui_key ctrl+a
    gui_type "tester"
    gui_key Tab
    gui_key ctrl+a
    gui_type "spacedtest"
    gui_key Tab
    gui_type "spacedtest1"
    gui_key Tab
    gui_type "spacedtest1"
    sleep 1
    page_capture 8-users-filled

    click_next
    # The summary page is the only page that talks about mount points and the
    # boot loader. OCR reads "boot loader" as two words, so match on words.
    if ! gui_wait "mount point" 60 && ! gui_wait "boot loader" 60; then
        page_capture 9-summary-missing
        echo "The summary page did not appear"
        return 1
    fi
    page_capture 9-summary
    return 0
}

# ---------------------------------------------------------------------------
# f. verify the installed system on the disk (still the live session)
# ---------------------------------------------------------------------------
verify_install() {
    local home_uuid=$1
    guest_ssh 'bash -s' <<VERIFY
set -e
mkdir -p /mnt/t /mnt/v02check
umount --recursive /mnt/t 2>/dev/null || true
umount --recursive /mnt/v02check 2>/dev/null || true
mount -o ro /dev/vda1 /mnt/t
mount -o ro /dev/vda2 /mnt/v02check
echo "FSTAB:"
cat /mnt/t/etc/fstab
echo "FSTAB_HOME:"
grep -E '^[^[:space:]]+[[:space:]]+/home([[:space:]]|\$)' /mnt/t/etc/fstab || echo MISSING
echo "HOME_UUID=$home_uuid"
echo "KEEP_OLDUSER:"
cat /mnt/v02check/olduser/keep.txt 2>/dev/null || echo LOST
echo "KEEP_USER:"
cat /mnt/v02check/user/keep.txt 2>/dev/null || echo LOST
echo "HOME_DIRS:"
ls /mnt/v02check
echo "RESCUE_TOOLS:"
ls -1 /mnt/t/usr/bin /mnt/t/usr/sbin 2>/dev/null | grep -x -E 'gparted|testdisk|photorec|ddrescue|smartctl|lvm' || echo none
echo "OS_RELEASE:"
grep -E '^(NAME|VERSION)=' /mnt/t/etc/os-release || true
VERIFY
}

echo "Starting reused-home install test on $ISO ($RAM MiB, $CPUS CPUs, KVM/BIOS, SSH 127.0.0.1:$SSH_PORT)"
# A leftover VM from an earlier run would answer on the SSH port and this test
# would drive the wrong machine.
if ( exec 3<>"/dev/tcp/127.0.0.1/$SSH_PORT" ) 2>/dev/null; then
    exec 3<&-
    exec 3>&-
    echo "Something already listens on 127.0.0.1:$SSH_PORT; stop that VM first" >&2
    exit 2
fi
echo "Artifacts: $OUT"
if ! qemu-img create -f qcow2 "$DISK" "$DISK_SIZE" > "$OUT/qemu-img.log" 2>&1; then
    echo "Could not create $DISK; see $OUT/qemu-img.log" >&2
    exit 2
fi
qemu-system-x86_64 -enable-kvm -cpu host -m "$RAM" -smp "$CPUS" \
    -device qemu-xhci,id=xhci \
    -device usb-kbd,bus=xhci.0 -device usb-tablet,bus=xhci.0 \
    -nic "user,model=virtio-net-pci,hostfwd=tcp:127.0.0.1:$SSH_PORT-:22" \
    -rtc base=utc -vga std -global VGA.vgamem_mb=64 \
    -display none -vnc "127.0.0.1:$VNC_DISPLAY" \
    -serial "file:$OUT/qemu-serial.log" \
    -qmp "unix:$QMP_SOCKET,server=on,wait=off" \
    -drive "if=virtio,file=$DISK" \
    -cdrom "$ISO" -boot order=d > "$OUT/qemu.log" 2>&1 &
QEMU_PID=$!
echo "QEMU PID $QEMU_PID (log: $OUT/qemu.log)"

if ! wait_for_ssh "$BOOT_TIMEOUT"; then
    echo "The live ISO never offered SSH on port $SSH_PORT within ${BOOT_TIMEOUT}s; see $OUT/qemu.log" >&2
    exit 2
fi
echo "Live ISO is up after ${SECONDS}s"

DESKTOP_READY=no
started=$SECONDS
while (( SECONDS - started < DESKTOP_TIMEOUT )); do
    if guest_ssh 'pgrep -x mate-panel >/dev/null && pgrep -x compiz >/dev/null' >/dev/null 2>&1; then
        DESKTOP_READY=yes
        break
    fi
    echo "Waiting for the live desktop ($((SECONDS - started))s/${DESKTOP_TIMEOUT}s)"
    sleep "$POLL"
done
if [ "$DESKTOP_READY" != yes ]; then
    echo "The live desktop did not start within ${DESKTOP_TIMEOUT}s" >&2
    exit 2
fi
echo "Live desktop is up after $((SECONDS - started))s"
if [ -n "$LIVE_PREP" ]; then
    echo "Live-session preparation (diagnostic): $LIVE_PREP"
    if ! guest_ssh "$LIVE_PREP"; then
        echo "SPACED_V2_LIVE_PREP failed in the live session" >&2
        exit 2
    fi
fi
# The install takes many minutes; a blank or DPMS-blanked screen would blind the OCR.
gui_x xset s off -dpms >/dev/null 2>&1 || true
echo "Screen geometry: $(gui_x xdotool getdisplaygeometry 2>/dev/null || echo unknown)"

# shellcheck disable=SC2016  # the date/pid run in the guest, not here
MARKER=$(guest_ssh 'printf %s "$(date +%s)-$$"')
echo "Preparing the previous installation on /dev/vda (marker $MARKER)"
PREPARE_OUT=$(prepare_old_system "$MARKER") || {
    echo "Could not prepare the previous installation:" >&2
    printf '%s\n' "$PREPARE_OUT" >&2
    exit 2
}
printf '%s\n' "$PREPARE_OUT"
HOME_UUID=$(printf '%s\n' "$PREPARE_OUT" | sed -n 's/^HOME_UUID=//p' | tail -1)
if [ -z "$HOME_UUID" ]; then
    echo "No HOME_UUID from the disk preparation" >&2
    exit 2
fi
echo "HOME_UUID=$HOME_UUID"

guest_ssh 'os-prober' > "$OUT/os-prober.txt" 2>&1 || true
echo "os-prober output:"
cat "$OUT/os-prober.txt"
if ! grep -q '/dev/vda1' "$OUT/os-prober.txt"; then
    echo "os-prober does not list /dev/vda1; the installer may not offer 'Replace a partition'" >&2
fi

walked=no
for attempt in $(seq 1 "$WALK_TRIES"); do
    echo "Installer walk attempt $attempt of $WALK_TRIES"
    start_installer
    if walk_to_summary; then
        walked=yes
        break
    fi
    echo "Walk attempt $attempt failed; restarting the installer"
    stop_installer
done
if [ "$walked" != yes ]; then
    echo "The installer could not be driven to the summary page after $WALK_TRIES attempts" >&2
    exit 2
fi

SUMMARY=$(tesseract "$PAGES/9-summary.png" - --psm 11 2>/dev/null || true)
if printf '%s\n' "$SUMMARY" | grep -qi 'home' && printf '%s\n' "$SUMMARY" | grep -qi 'vda2'; then
    echo "SUMMARY PROMISES /home ON vda2"
else
    echo "SUMMARY DOES NOT PROMISE /home ON vda2" >&2
fi

# The summary page's Install button is Alt+I: the sidebar also contains the
# word "Install", so clicking the first OCR match would hit the sidebar.
echo "Starting the installation (Alt+I)"
gui_key alt+i
sleep 3
page_capture 10-after-install-key
if gui_find "Start installing" >/dev/null 2>&1; then
    echo "Confirming the install dialog"
    gui_click "Start installing"
elif gui_find "Cancel Installation" >/dev/null 2>&1; then
    echo "A cancel dialog is in the way" >&2
    exit 2
fi

finished=no
failed=no
started=$SECONDS
while (( SECONDS - started < INSTALL_TIMEOUT )); do
    if ! installer_alive; then
        echo "Calamares is no longer running $((SECONDS - started))s into the installation" >&2
        page_capture 11-installer-gone
        # shellcheck disable=SC2016  # the $f loop runs in the guest
        guest_ssh 'for f in /root/.cache/calamares/session.log /home/user/.cache/calamares/session.log; do
            if [ -f "$f" ]; then echo "== $f =="; tail -120 "$f"; fi
        done' > "$OUT/session-failed.log" 2>&1 || true
        exit 1
    fi
    if gui_find "All done" >/dev/null 2>&1; then
        finished=yes
        break
    fi
    if gui_find "Installation Failed" >/dev/null 2>&1; then
        failed=yes
        break
    fi
    # Fallback if the finished page heading is not readable: the exec page has
    # a "Toggle log" button, the finished page has a restart button instead.
    if ! gui_find "Toggle log" >/dev/null 2>&1 && gui_find "Restart" >/dev/null 2>&1; then
        finished=yes
        break
    fi
    echo "Installing ($((SECONDS - started))s/${INSTALL_TIMEOUT}s)"
    sleep 15
done
page_capture 11-finished
if [ "$failed" = yes ]; then
    # shellcheck disable=SC2016  # the $f loop runs in the guest
    guest_ssh 'for f in /root/.cache/calamares/session.log /home/user/.cache/calamares/session.log; do
        if [ -f "$f" ]; then echo "== $f =="; tail -200 "$f"; fi
    done' > "$OUT/session-failed.log" 2>&1 || true
    echo "Calamares reported a failed installation; see $OUT/session-failed.log" >&2
    exit 1
fi
if [ "$finished" != yes ]; then
    echo "The installer did not finish within ${INSTALL_TIMEOUT}s" >&2
    exit 2
fi

echo "Copying the Calamares session log and the installed fstab"
# shellcheck disable=SC2016  # the $f loop runs in the guest
guest_ssh 'for f in /root/.cache/calamares/session.log /home/user/.cache/calamares/session.log; do
    if [ -f "$f" ]; then echo "== $f =="; cat "$f"; fi
done' > "$OUT/session.log" 2>&1 || true

VERIFY_OUT=$(verify_install "$HOME_UUID") || {
    echo "The installed system could not be inspected:" >&2
    printf '%s\n' "$VERIFY_OUT" >&2
    exit 2
}
printf '%s\n' "$VERIFY_OUT" > "$OUT/verify.txt"
printf '%s\n' "$VERIFY_OUT"

FSTAB_HOME=$(printf '%s\n' "$VERIFY_OUT" | sed -n '/^FSTAB_HOME:/,/^HOME_UUID=/p' \
    | sed '1d;$d' | grep -v '^$' | head -1)
KEEP_OLDUSER=$(printf '%s\n' "$VERIFY_OUT" | sed -n '/^KEEP_OLDUSER:/,/^KEEP_USER:/p' \
    | sed '1d;$d' | grep -v '^$' | head -1)
KEEP_USER=$(printf '%s\n' "$VERIFY_OUT" | sed -n '/^KEEP_USER:/,/^HOME_DIRS:/p' \
    | sed '1d;$d' | grep -v '^$' | head -1)
RESCUE=$(printf '%s\n' "$VERIFY_OUT" | sed -n '/^RESCUE_TOOLS:/,/^OS_RELEASE:/p' \
    | sed '1d;$d' | grep -v '^$' | paste -sd, -)
[ -n "$RESCUE" ] || RESCUE=none

printf '%s\n' "$VERIFY_OUT" | sed -n '/^FSTAB:/,/^FSTAB_HOME:/p' | sed '1d;$d' \
    > "$OUT/installed-etc-fstab"

fstab_ok=no
case "$FSTAB_HOME" in
    MISSING | '') ;;
    *) case "$FSTAB_HOME" in *"$HOME_UUID"*) fstab_ok=yes ;; esac ;;
esac
keep_olduser=LOST
case "$KEEP_OLDUSER" in "KEEP-OLDUSER-$MARKER") keep_olduser=ok ;; esac
keep_user=LOST
case "$KEEP_USER" in "KEEP-USER-$MARKER") keep_user=ok ;; esac

echo "INFO: fstab_home_ok=$fstab_ok home_uuid=$HOME_UUID"
rescue_ok=yes
case "$ISO_NAME" in
    *11.26.1*)
        if [ "$RESCUE" != none ]; then
            rescue_ok=no
            echo "INFO: rescue tools are live-only and must not be installed: $RESCUE"
        fi
        ;;
esac

if [ "$fstab_ok" = yes ] && [ "$keep_olduser" = ok ] && [ "$keep_user" = ok ] \
        && [ "$rescue_ok" = yes ]; then
    echo "RESULT: PASS fstab_home=$FSTAB_HOME keep_olduser=$keep_olduser keep_user=$keep_user rescue_tools_installed=$RESCUE"
    exit 0
fi
echo "RESULT: FAIL fstab_home=$FSTAB_HOME keep_olduser=$keep_olduser keep_user=$keep_user rescue_tools_installed=$RESCUE"
exit 1
