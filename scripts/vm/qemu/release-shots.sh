#!/bin/bash
# Spaced Linux 11.26.1 release screenshots for the GitHub release page.
#
# Boot the released live ISO headless in KVM/BIOS the way scripts/vm/qemu/
# live-checks.sh does, force a 1920x1080 desktop inside the guest, then take one
# QMP screendump per release feature: the clean desktop, Spaced Monitor, Spaced
# Welcome, Caja's "Set as Wallpaper…" menu, the live rescue tools (GParted plus
# the desktop password note) and Spaced Update on the OS Release tab.
#
# Every shot is measured (exact size, not black, not one flat colour), the
# window list of the moment it was taken is stored next to it, and when
# tesseract is installed the text is read back out of the pixels to prove the
# right window is visible. PNG + q90 WebP copies land in
# docs/releases/<VERSION>/images/ with a README.md.
#
# Output: one PASS:/FAIL:/INFO: line per check and a final
# "RESULT: PASS|FAIL passed=<n> failed=<n>".
set -euo pipefail

usage() {
    cat >&2 <<'USAGE'
Usage: release-shots.sh ISO

Boot the live ISO headless in QEMU (KVM, BIOS, -boot order=d, -display none,
VNC + QMP only), set the guest desktop to 1920x1080 with xrandr, then capture
the six 11.26.1 release screenshots with QMP screendump:

  shot-desktop-dark.png               clean live desktop, default dark theme
  shot-spaced-monitor.png             Spaced Monitor with live numbers
  shot-spaced-welcome.png             Spaced Welcome, first page
  shot-caja-set-wallpaper.png         Caja picture selected + context menu
  shot-live-rescue-gparted.png        GParted open + desktop password note
  shot-spaced-update-os-release.png   Spaced Update, OS Release tab

Each shot is validated with PIL (exact size, std-dev > 10, < 30 % pure black)
and, when tesseract is installed, checked by reading text back out of the
pixels. PNG + WebP (quality 90) are written to
docs/releases/<VERSION>/images/ together with README.md.

Exit codes: 0 = PASS, 1 = FAIL, 2 = could not run.
Artifacts: build/vm-tests/r01/<iso-name>/
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
SSH_PORT=${SPACED_VM_SSH_PORT:-2233}
VNC_DISPLAY=${SPACED_QEMU_VNC_DISPLAY:-44}
RAM=${SPACED_QEMU_RAM:-4096}
CPUS=${SPACED_QEMU_CPUS:-4}
XRES=${SPACED_SHOTS_XRES:-1920}
YRES=${SPACED_SHOTS_YRES:-1080}
ROOT_PASSWORD=${SPACED_LIVE_ROOT_PASSWORD:-spaced}
BOOT_TIMEOUT=${SPACED_ISO_BOOT_TIMEOUT:-300}
DESKTOP_TIMEOUT=${SPACED_DESKTOP_TIMEOUT:-180}
POLL=${SPACED_VM_POLL:-5}
RELEASE_VERSION=$(cat "$PROJECT_ROOT/VERSION")
ISO_NAME=${ISO##*/}
ISO_NAME=${ISO_NAME%.iso}
OUT=${SPACED_RELEASE_SHOTS_DIR:-$PROJECT_ROOT/build/vm-tests/r01/$ISO_NAME}
DOCS_DIR=${SPACED_RELEASE_SHOTS_DOCS_DIR:-$PROJECT_ROOT/docs/releases/$RELEASE_VERSION/images}
# The live image ships no pictures in ~/, so the Caja shot uses one of the
# wallpapers that are already on the ISO.
SHOT_PICTURE=${SPACED_SHOTS_PICTURE:-solarsystem.jpg}

for value in "$SSH_PORT" "$VNC_DISPLAY" "$RAM" "$CPUS" "$XRES" "$YRES" \
             "$BOOT_TIMEOUT" "$DESKTOP_TIMEOUT"; do
    [[ "$value" =~ ^[0-9]+$ ]] || { echo "Invalid numeric VM setting: $value" >&2; exit 2; }
done
for tool in qemu-system-x86_64 sshpass ssh python3 pnmtopng sha256sum; do
    command -v "$tool" >/dev/null || { echo "$tool is required for the release shots" >&2; exit 2; }
done
if ! python3 -c 'from PIL import Image' >/dev/null 2>&1; then
    echo "python3 Pillow (PIL) is required to measure and convert the shots" >&2
    exit 2
fi
if [ ! -e /dev/kvm ]; then
    echo "The release shots need KVM (/dev/kvm): a real live desktop must be photographed" >&2
    exit 2
fi
ISO_SHA256=$(sha256sum "$ISO" | cut -d' ' -f1)

mkdir -p "$OUT"
OUT=$(cd "$OUT" && pwd)
QMP_SOCKET="$OUT/qmp.sock"
# Remove evidence of a previous run so an old screenshot can never be mistaken
# for one taken from this ISO.
rm -f "$OUT"/qemu.log "$OUT"/qemu-serial.log "$OUT"/shot-*.png "$OUT"/shot-*.webp \
      "$OUT"/shot-*.ppm "$OUT"/shot-*.windows.txt "$OUT"/shot-*.ocr.txt \
      "$OUT"/README.md "$OUT"/qmp.sock

QEMU_PID=''
PASSED=0
FAILED=0
SHOT_NAMES=()
SHOT_LABELS=()
SHOT_NOTES=()

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

pass() { echo "PASS: $1"; PASSED=$((PASSED + 1)); }
fail() { echo "FAIL: $1"; FAILED=$((FAILED + 1)); }
info() { echo "INFO: $1"; }

# Root shell in the guest; the script comes from stdin.
guest_root() {
    SSHPASS="$ROOT_PASSWORD" sshpass -e ssh -p "$SSH_PORT" -o ConnectTimeout=10 \
        -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        root@127.0.0.1 'bash -s'
}

# One-line root command (stdin closed so ssh can never wait on the caller).
root_cmd() {
    SSHPASS="$ROOT_PASSWORD" sshpass -e ssh -p "$SSH_PORT" -o ConnectTimeout=10 \
        -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        root@127.0.0.1 "$1" < /dev/null
}

# GUI programs of the live session: X display :0 belongs to the live user.
guest_gui() {
    SSHPASS="$ROOT_PASSWORD" sshpass -e ssh -p "$SSH_PORT" -o ConnectTimeout=10 \
        -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        root@127.0.0.1 "su - user -c 'DISPLAY=:0 XAUTHORITY=/home/user/.Xauthority bash -s'"
}

gui_cmd() {
    SSHPASS="$ROOT_PASSWORD" sshpass -e ssh -p "$SSH_PORT" -o ConnectTimeout=10 \
        -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        root@127.0.0.1 \
        "su - user -c 'DISPLAY=:0 XAUTHORITY=/home/user/.Xauthority $1'" < /dev/null
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

capture_screen() {
    python3 - "$QMP_SOCKET" "$1" <<'PY'
import json
import socket
import sys
with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
    sock.settimeout(10)
    sock.connect(sys.argv[1])
    stream = sock.makefile('rwb')
    json.loads(stream.readline())
    for request in ({'execute': 'qmp_capabilities'},
                    {'execute': 'screendump', 'arguments': {'filename': sys.argv[2]}}):
        stream.write(json.dumps(request).encode() + b'\n')
        stream.flush()
        while True:
            result = json.loads(stream.readline())
            if 'error' in result:
                raise SystemExit(str(result['error']))
            if 'return' in result:
                break
PY
}

# Measure the shot and write the WebP copy; a bad measurement is fatal for it.
validate_shot() {
    python3 - "$1" "$2" "$XRES" "$YRES" <<'PY'
import sys
from PIL import Image, ImageStat
png, webp = sys.argv[1], sys.argv[2]
im = Image.open(png).convert('RGB')
w, h = im.size
if (w, h) != (int(sys.argv[3]), int(sys.argv[4])):
    print(f'size is {w}x{h}, expected {sys.argv[3]}x{sys.argv[4]}')
    raise SystemExit(1)
std = ImageStat.Stat(im.convert('L')).stddev[0]
raw = im.tobytes()
data = [tuple(raw[i:i + 3]) for i in range(0, len(raw), 3)]
black = sum(1 for p in data if p == (0, 0, 0)) / len(data)
print(f'{w}x{h} stddev={std:.1f} pure_black={black * 100:.1f}% colours={len(set(data))}')
if std <= 10.0:
    raise SystemExit(1)
if black >= 0.30:
    raise SystemExit(1)
im.save(webp, 'WEBP', quality=90, method=6)
PY
}

# Read the pixels back with tesseract: proves the window really drew.
ocr_shot() {
    local png=$1 x=$2 y=$3 w=$4 h=$5 crop=$6 tesseract
    tesseract=$(command -v tesseract || true)
    [ -n "$tesseract" ] || return 2
    python3 - "$png" "$x" "$y" "$w" "$h" "$crop" <<'PY' || return 1
import sys
from PIL import Image, ImageOps
im = Image.open(sys.argv[1]).convert('RGB')
x, y, w, h = (max(0, int(v)) for v in sys.argv[2:6])
crop = im.crop((x, y, min(im.width, x + w), min(im.height, y + h)))
crop = crop.resize((crop.width * 2, crop.height * 2), Image.LANCZOS)
ImageOps.invert(crop.convert('L')).save(sys.argv[6])
PY
    "$tesseract" "$crop" - --psm 6 2>/dev/null
}

# Close every application window; the panel and the desktop window stay.
close_windows() {
    guest_gui <<'EOS' || true
for w in $(wmctrl -l | grep -vE ' (Desktop|Bottom Panel)$' | awk '{print $1}'); do
    xdotool windowclose "$w" 2>/dev/null
done
EOS
    sleep 2
}

# Wait until a window whose title matches $1 exists; print its id.
wait_window() {
    local pattern=$1 limit=$2 waited=0 id=''
    while [ "$waited" -lt "$limit" ]; do
        id=$(guest_gui <<EOS
wmctrl -l | grep -E '$pattern' | head -n 1 | awk '{print \$1}'
EOS
)
        id=$(printf '%s' "$id" | tr -dc 'x0-9a-fA-F')
        if [ -n "$id" ]; then
            printf '%s\n' "$id"
            return 0
        fi
        sleep 2
        waited=$((waited + 2))
    done
    return 1
}

# "x y w h" of a window as it is really mapped on screen.
window_geom() {
    local geom=''
    geom=$(guest_gui <<EOS
xwininfo -id $1 2>/dev/null | sed -n 's/.*Absolute upper-left X: //p;s/.*Absolute upper-left Y: //p;s/.*Width: //p;s/.*Height: //p' | tr '\n' ' '
EOS
)
    printf '%s\n' "$geom" | tr -s ' ' | sed 's/^ //;s/ $//'
}

move_window() {
    gui_cmd "wmctrl -i -r $1 -e 0,$2,$3,$4,$5" >/dev/null || true
    sleep 1
}

launch_as_user() {
    local pid=''
    pid=$(guest_gui <<EOS
setsid $1 >/dev/null 2>&1 </dev/null &
echo \$!
EOS
)
    printf '%s' "$pid" | tr -dc '0-9'
}

# GParted escalates through polkit, which has no agent in an ssh-spawned shell;
# on the live stick the rule in etc/polkit-1/rules.d lets the session run it
# without a password, so start it as root on the live user's display instead.
launch_as_root() {
    local pid=''
    pid=$(guest_root <<EOS
DISPLAY=:0 XAUTHORITY=/home/user/.Xauthority setsid $1 >/dev/null 2>&1 </dev/null &
echo \$!
EOS
)
    printf '%s' "$pid" | tr -dc '0-9'
}

# screendump -> PNG + WebP, with the window list and the OCR text next to it.
# $8 = comma separated words that must all be readable in the OCR region.
# A frame that is black or one flat colour is retaken (the desktop and the
# window must finish drawing), up to 6 attempts.
take_shot() {
    local name=$1 label=$2 note=$3 x=$4 y=$5 w=$6 h=$7 expect=$8
    local ppm="$OUT/shot-$name.ppm" png="$OUT/shot-$name.png"
    local webp="$OUT/shot-$name.webp" stats='' status=0 attempt=1
    while true; do
        status=0
        if ! capture_screen "$ppm"; then
            fail "$label: QMP screendump"
            return 1
        fi
        if ! pnmtopng "$ppm" > "$png" 2>/dev/null; then
            fail "$label: PPM to PNG conversion"
            return 1
        fi
        stats=$(validate_shot "$png" "$webp") || status=$?
        if [ "$status" -eq 0 ]; then
            break
        fi
        if [ "$attempt" -ge 6 ]; then
            fail "$label: image measurement after $attempt frames (${stats:-no measurement})"
            return 1
        fi
        info "$label: frame $attempt is not drawn yet (${stats:-no measurement}), waiting"
        attempt=$((attempt + 1))
        sleep 3
    done
    pass "$label: image measured in frame $attempt ($stats)"
    gui_cmd 'wmctrl -lpG' > "$OUT/shot-$name.windows.txt" 2>/dev/null || true
    if command -v tesseract >/dev/null; then
        local text='' ocr_status=0
        text=$(ocr_shot "$png" "$x" "$y" "$w" "$h" "$OUT/shot-$name.crop.png") || ocr_status=$?
        if [ "$ocr_status" -eq 2 ]; then
            info "$label: tesseract unusable"
        elif [ -z "$text" ]; then
            fail "$label: readable text found in the pixels"
        else
            printf '%s\n' "$text" > "$OUT/shot-$name.ocr.txt"
            local missing='' want
            if [ -n "$expect" ]; then
                while IFS= read -r want; do
                    [ -n "$want" ] || continue
                    printf '%s' "$text" | grep -qiF "$want" || missing="$missing '$want'"
                done < <(printf '%s\n' "$expect" | tr ',' '\n')
            fi
            if [ -n "$missing" ]; then
                fail "$label:$missing readable in the pixels"
            else
                pass "$label: text readable in the pixels${expect:+ ($expect)}"
            fi
        fi
    else
        info "$label: tesseract not installed, pixels not read back"
    fi
    rm -f "$ppm" "$OUT/shot-$name.crop.png"
    SHOT_NAMES+=("$name")
    SHOT_LABELS+=("$label")
    SHOT_NOTES+=("$note")
    return 0
}

echo "Starting release shots on $ISO ($RAM MiB, $CPUS CPUs, KVM/BIOS, SSH 127.0.0.1:$SSH_PORT)"
echo "ISO sha256: $ISO_SHA256"
echo "Artifacts: $OUT"
qemu-system-x86_64 -enable-kvm -cpu host -m "$RAM" -smp "$CPUS" \
    -device qemu-xhci,id=xhci \
    -device usb-kbd,bus=xhci.0 -device usb-tablet,bus=xhci.0 \
    -nic "user,model=virtio-net-pci,hostfwd=tcp:127.0.0.1:$SSH_PORT-:22" \
    -rtc base=utc -vga virtio \
    -display none -vnc "127.0.0.1:$VNC_DISPLAY" \
    -serial "file:$OUT/qemu-serial.log" \
    -qmp "unix:$QMP_SOCKET,server=on,wait=off" \
    -cdrom "$ISO" -boot order=d > "$OUT/qemu.log" 2>&1 &
QEMU_PID=$!
printf '%s\n' "$QEMU_PID" > "$OUT/qemu.pid"
echo "QEMU PID $QEMU_PID (log: $OUT/qemu.log)"

started=$SECONDS
while (( SECONDS - started < BOOT_TIMEOUT )); do
    if ! kill -0 "$QEMU_PID" 2>/dev/null; then
        echo "The VM exited early; see $OUT/qemu.log" >&2
        exit 2
    fi
    if ssh_is_ready 2>/dev/null && [ "$(root_cmd 'printf ok')" = ok ]; then
        break
    fi
    echo "Waiting for live SSH ($((SECONDS - started))s/${BOOT_TIMEOUT}s)"
    sleep "$POLL"
done
if ! ssh_is_ready 2>/dev/null; then
    echo "The live ISO never offered SSH on port $SSH_PORT within ${BOOT_TIMEOUT}s" >&2
    exit 2
fi
info "live_ssh_seconds=$((SECONDS - started))"

started=$SECONDS
while (( SECONDS - started < DESKTOP_TIMEOUT )); do
    if root_cmd 'pgrep -x mate-panel >/dev/null && pgrep -x caja >/dev/null && pgrep -x compiz >/dev/null'; then
        break
    fi
    echo "Waiting for the live desktop ($((SECONDS - started))s/${DESKTOP_TIMEOUT}s)"
    sleep "$POLL"
done
if ! root_cmd 'pgrep -x mate-panel >/dev/null && pgrep -x caja >/dev/null && pgrep -x compiz >/dev/null'; then
    echo "mate-panel, caja and compiz never all ran; the desktop cannot be photographed" >&2
    exit 2
fi
info "desktop_ready_uptime=$(root_cmd 'cut -d. -f1 /proc/uptime')"

# Full HD: virtio-gpu offers 1920x1080 in its EDID, xrandr switches to it.
OUTPUT=$(guest_gui <<'EOS'
xrandr | awk '/ connected primary/ {print $1; exit}'
EOS
)
OUTPUT=$(printf '%s' "$OUTPUT" | tr -dc 'A-Za-z0-9-')
if [ -z "$OUTPUT" ]; then
    echo "No connected X output found; cannot set ${XRES}x${YRES}" >&2
    exit 2
fi
gui_cmd "xrandr --output $OUTPUT --mode ${XRES}x${YRES} --rate 60 || xrandr --output $OUTPUT --mode ${XRES}x${YRES}" >/dev/null
sleep 3
GEOM=$(gui_cmd 'xdotool getdisplaygeometry' | tr -d '\r')
if [ "$(printf '%s' "$GEOM" | tr -s ' ')" != "$XRES $YRES" ]; then
    echo "The guest desktop is '$GEOM', not ${XRES}x${YRES}" >&2
    exit 2
fi
pass "live desktop runs at ${XRES}x${YRES} on output $OUTPUT"

# A mode switch can leave a black framebuffer for a few seconds; wait until the
# desktop has really painted before photographing anything.
PAINTED=no
for _ in {1..20}; do
    if capture_screen "$OUT/paint.ppm" && pnmtopng "$OUT/paint.ppm" > "$OUT/paint.png" 2>/dev/null &&
        validate_shot "$OUT/paint.png" "$OUT/paint.webp" > /dev/null 2>&1; then
        PAINTED=yes
        break
    fi
    sleep 3
done
rm -f "$OUT"/paint.ppm "$OUT"/paint.png "$OUT"/paint.webp
if [ "$PAINTED" != yes ]; then
    echo "The live desktop never painted a frame at ${XRES}x${YRES}" >&2
    exit 2
fi
info 'the desktop finished painting after the mode switch'

# The live image has no pictures in ~/, and the Caja shot needs one.
if guest_root <<EOS
set -e
test -f "/usr/share/backgrounds/spaced/$SHOT_PICTURE"
mkdir -p /home/user/Pictures
rm -f /home/user/Pictures/*
cp "/usr/share/backgrounds/spaced/$SHOT_PICTURE" /home/user/Pictures/
chown -R user:user /home/user/Pictures
EOS
then
    pass "live user has /home/user/Pictures/$SHOT_PICTURE for the Caja shot"
else
    fail "live user has /home/user/Pictures/$SHOT_PICTURE for the Caja shot"
fi

# ------------------------------------------------------------- a. the hero shot
close_windows
sleep 4
take_shot desktop-dark 'a: clean desktop with the default theme' \
    'Clean live desktop: default Spaced-Linux-Dark theme, wallpaper, bottom panel and the live desktop icons (Install Spaced Linux, Live session passwords.txt), no windows open.' \
    0 0 "$XRES" "$YRES" 'Live session,passwords,Menu' || true

# ----------------------------------------------------------- b. Spaced Monitor
close_windows
MONITOR_PID=$(launch_as_user spaced-monitor)
if MONITOR_ID=$(wait_window 'Spaced Monitor' 40); then
    MONITOR_GEOM=$(window_geom "$MONITOR_ID")
    read -r MX MY MW MH <<< "$MONITOR_GEOM"
    sleep 8
    take_shot spaced-monitor 'b: Spaced Monitor window' \
        'Spaced Monitor 0.1.9 main window with live CPU, memory, disk and network numbers.' \
        "${MX:-0}" "${MY:-0}" "${MW:-$XRES}" "${MH:-$YRES}" 'Spaced Monitor' || true
else
    fail 'b: Spaced Monitor window appeared'
fi
[ -z "$MONITOR_PID" ] || root_cmd "kill $MONITOR_PID" >/dev/null 2>&1 || true
close_windows

# ---------------------------------------------------------- c. Spaced Welcome
close_windows
WELCOME_PID=$(launch_as_user spaced-welcome)
if WELCOME_ID=$(wait_window 'Welcome to Spaced Linux' 40); then
    # The window is 984x720 and the WM drops it partly off the bottom edge.
    move_window "$WELCOME_ID" 468 170 984 720
    WELCOME_GEOM=$(window_geom "$WELCOME_ID")
    read -r WX WY WW WH <<< "$WELCOME_GEOM"
    sleep 3
    take_shot spaced-welcome 'c: Spaced Welcome first page' \
        'Spaced Welcome 0.1.22, first page, exactly as the live user sees it.' \
        "${WX:-0}" "${WY:-0}" "${WW:-$XRES}" "${WH:-$YRES}" 'Version 0.1.22' || true
else
    fail 'c: Spaced Welcome window appeared'
fi
[ -z "$WELCOME_PID" ] || root_cmd "kill $WELCOME_PID" >/dev/null 2>&1 || true
close_windows

# ------------------------------------------------ d. Caja "Set as Wallpaper…"
close_windows
CAJA_PID=$(launch_as_user "caja --no-default-window --browser --select file:///home/user/Pictures/$SHOT_PICTURE")
CAJA_ID=$(wait_window ' Pictures$' 30) || CAJA_ID=''
if [ -n "$CAJA_ID" ]; then
    move_window "$CAJA_ID" 480 190 960 660
    guest_gui <<EOS
xdotool windowactivate --sync $CAJA_ID
sleep 1
xdotool key --clearmodifiers ctrl+equal
xdotool key --clearmodifiers ctrl+equal
xdotool key --clearmodifiers ctrl+equal
EOS
    sleep 3
    CAJA_GEOM=$(window_geom "$CAJA_ID")
    read -r CX CY CW CH <<< "$CAJA_GEOM"
    # Locate the picture's icon: the most colourful block inside the icon view.
    capture_screen "$OUT/locate.ppm" || true
    ICON=$(python3 - "$OUT/locate.ppm" "$CX" "$CY" "$CW" "$CH" <<'PY'
import re
import sys
from pathlib import Path
raw = Path(sys.argv[1]).read_bytes()
head = re.match(rb'P6\s+(\d+)\s+(\d+)\s+255\s', raw)
if not head:
    raise SystemExit('locate shot is not an RGB PPM image')
w, h = (int(v) for v in head.groups())
body = raw[head.end():]
x0, y0, cw, ch = (int(v) for v in sys.argv[2:6])
# icon view = right of the sidebar, below the toolbars, above the statusbar
left, top = x0 + 220, y0 + 110
right, bottom = min(w, x0 + cw), min(h, y0 + ch - 60)
best = None
for y in range(top, bottom, 2):
    row = (y * w) * 3
    for x in range(left, right, 2):
        o = row + x * 3
        r, g, b = body[o], body[o + 1], body[o + 2]
        if max(r, g, b) > 90 and max(r, g, b) - min(r, g, b) > 60:
            if best is None:
                best = [x, y, x, y]
            else:
                best[0] = min(best[0], x); best[1] = min(best[1], y)
                best[2] = max(best[2], x); best[3] = max(best[3], y)
if best is None:
    raise SystemExit('no colourful icon found in the Caja icon view')
print(f'{(best[0] + best[2]) // 2} {(best[1] + best[3]) // 2} {best[2] - best[0]} {best[3] - best[1]}')
PY
) || ICON=''
    if [ -n "$ICON" ]; then
        read -r IX IY IW IH <<< "$ICON"
        info "caja picture icon found at $IX,$IY (${IW}x${IH})"
        gui_cmd "xdotool mousemove $IX $IY click 3" >/dev/null
        sleep 2
        # The popup opens at the pointer; OCR the popup area, not the whole window.
        take_shot caja-set-wallpaper 'd: Caja context menu with Set as Wallpaper' \
            'Caja with the picture selected and its right-click menu open, showing the "Set as Wallpaper…" action added for issue #303.' \
            "$IX" "$IY" 420 400 'Wallpaper' || true
        gui_cmd 'xdotool key --clearmodifiers Escape' >/dev/null || true
    else
        fail 'd: picture icon located in the Caja icon view'
    fi
else
    fail 'd: Caja window appeared'
fi
[ -z "$CAJA_PID" ] || root_cmd "kill $CAJA_PID" >/dev/null 2>&1 || true
close_windows

# ------------------------------------------ e. live rescue tools (GParted, etc.)
close_windows
gui_cmd 'xhost +si:localuser:root' >/dev/null 2>&1 || true
GPARTED_PID=$(launch_as_root /usr/sbin/gparted)
if GPARTED_ID=$(wait_window 'GParted$' 60); then
    # Move it right so the live desktop icons stay visible at the left edge.
    move_window "$GPARTED_ID" 880 280 920 640
    GPARTED_GEOM=$(window_geom "$GPARTED_ID")
    info "gparted window geometry: $GPARTED_GEOM"
    sleep 6
    take_shot live-rescue-gparted 'e: GParted plus the live password note' \
        'Live session rescue tools: GParted open on the live stick device, with the desktop note "Live session passwords.txt" beside it.' \
        0 0 "$XRES" "$YRES" 'GParted,passwords' || true
    # The desktop note must be readable in the same frame.
    if grep -qiF 'passwords' "$OUT/shot-live-rescue-gparted.ocr.txt" 2>/dev/null; then
        pass 'e: desktop note readable in the same frame'
    else
        info 'e: desktop note not confirmed by OCR (small text); see the saved window list'
    fi
else
    fail 'e: GParted window appeared'
fi
[ -z "$GPARTED_PID" ] || root_cmd "kill $GPARTED_PID" >/dev/null 2>&1 || true
close_windows

# ------------------------------------------------------------- f. Spaced Update
close_windows
UPDATE_PID=$(launch_as_user spaced-update)
if UPDATE_ID=$(wait_window 'Spaced Update' 40); then
    UPDATE_GEOM=$(window_geom "$UPDATE_ID")
    read -r UX UY UW UH <<< "$UPDATE_GEOM"
    sleep 4
    take_shot spaced-update-os-release 'f: Spaced Update, OS Release tab' \
        'Spaced Update opened offline on the OS Release tab: the tab is the default view, so no network is needed for this shot.' \
        "$UX" "$UY" "$UW" "$UH" 'Spaced Update,Ready when you are,No update check yet' || true
else
    fail 'f: Spaced Update window appeared'
fi
[ -z "$UPDATE_PID" ] || root_cmd "kill $UPDATE_PID" >/dev/null 2>&1 || true
close_windows

# ------------------------------------------------- publish the images and README
if [ "${#SHOT_NAMES[@]}" -gt 0 ]; then
    mkdir -p "$DOCS_DIR"
    # Drop the images of a previous run first: a stale screenshot must never be
    # published as if it came from this ISO.
    rm -f "$DOCS_DIR"/shot-*.png "$DOCS_DIR"/shot-*.webp
    for name in "${SHOT_NAMES[@]}"; do
        cp "$OUT/shot-$name.png" "$DOCS_DIR/shot-$name.png"
        cp "$OUT/shot-$name.webp" "$DOCS_DIR/shot-$name.webp"
    done
    {
        printf '# Spaced Linux %s release images\n\n' "$RELEASE_VERSION"
        printf 'Screenshots of the released live ISO, taken headless in QEMU (KVM, BIOS,\n'
        printf '1920x1080) with scripts/vm/qemu/release-shots.sh and QMP screendump.\n\n'
        printf -- '- ISO: %s\n' "${ISO##*/}"
        printf -- '- ISO sha256: %s\n' "$ISO_SHA256"
        printf -- '- VM: KVM, BIOS, %s MiB RAM, %s CPUs, virtio-gpu at %sx%s, headless\n' \
            "$RAM" "$CPUS" "$XRES" "$YRES"
        printf -- '- Every PNG has a same-name .webp (quality 90) for the release page.\n'
        printf -- '- Window list and OCR text of every frame: build/vm-tests/r01/%s/\n' "$ISO_NAME"
        printf -- '  (shot-<name>.windows.txt proves which window was open,\n'
        printf -- '   shot-<name>.ocr.txt is the text read back out of the pixels).\n\n'
        printf '| file | shows | resolution |\n|---|---|---|\n'
        for i in "${!SHOT_NAMES[@]}"; do
            printf '| shot-%s.png / .webp | %s | %sx%s |\n' \
                "${SHOT_NAMES[$i]}" "${SHOT_NOTES[$i]}" "$XRES" "$YRES"
        done
    } > "$DOCS_DIR/README.md"
    pass "images and README.md written to $DOCS_DIR"
fi

echo "Artifacts: $OUT"
if [ "$FAILED" -eq 0 ] && [ "${#SHOT_NAMES[@]}" -eq 6 ]; then
    echo "RESULT: PASS passed=$PASSED failed=$FAILED"
    exit 0
fi
echo "RESULT: FAIL passed=$PASSED failed=$FAILED shots=${#SHOT_NAMES[@]}/6"
exit 1
