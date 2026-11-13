#!/bin/bash
# gui.sh — OCR-driven GUI helper for ONE running Spaced live VM (issue #413 test).
#
# Source this from a VM test script after that script has started QEMU:
#
#     . "$SCRIPT_DIR/gui.sh"
#
# Environment the caller must provide:
#   SPACED_VM_QMP_SOCKET      QMP unix socket of the running VM (required)
#   SPACED_VM_SSH_PORT        host port forwarded to the guest SSH (required)
#   SPACED_LIVE_ROOT_PASSWORD root password of the live session (default: spaced)
#   SPACED_GUI_DIR            where throwaway screenshots go (default: socket dir)
#   SPACED_GUI_SCALE          OCR enlargement factor (default: 2)
#
# Functions (all work on the currently displayed VM screen):
#   gui_shot FILE.png            QMP screendump -> PPM -> 2x PNG (plus FILE-invert.png)
#   gui_text                     OCR text of the current screen
#   gui_find "words"             prints "x y" (screen pixels) of the centre of the
#                                first OCR match of those consecutive words; exit 1
#                                when the words are not on screen
#   gui_click "words"            gui_find, then xdotool mousemove/click inside the VM
#   gui_click_xy X Y             click at screen coordinates
#   gui_type "text"              xdotool type inside the VM (as the live user)
#   gui_key KEY                  xdotool key inside the VM (as the live user)
#   gui_wait "words" SECONDS     poll gui_find every 3 s until found or timeout
#
# The installer is a dark Qt theme, so plain OCR often reads almost nothing;
# every search therefore tries the normal screenshot first and the inverted one
# second (see gui_shot).  gui_find divides the 2x enlargement out again, so the
# coordinates it prints are the ones xdotool needs inside the guest.

GUI_QMP=${SPACED_VM_QMP_SOCKET:-}
GUI_SSH_PORT=${SPACED_VM_SSH_PORT:-2232}
GUI_ROOT_PASSWORD=${SPACED_LIVE_ROOT_PASSWORD:-spaced}
GUI_SCALE=${SPACED_GUI_SCALE:-2}
GUI_TMP_DIR=${SPACED_GUI_DIR:-}

# python3 -c program: PPM -> enlarged PNG + inverted PNG.
GUI_SHOT_PY='
import sys
from PIL import Image, ImageOps

ppm, png, inverted, scale = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
if scale < 1:
    raise SystemExit("SPACED_GUI_SCALE must be at least 1")
image = Image.open(ppm).convert("RGB")
image = image.resize((image.width * scale, image.height * scale), Image.LANCZOS)
image.save(png)
ImageOps.invert(image).save(inverted)
'

# python3 -c program: read a tesseract TSV dump on argv[3], print the centre of
# the first occurrence of the consecutive query words (case-insensitively, all
# on one OCR line), divided by the enlargement factor.
GUI_FIND_PY='
import sys

query, scale, path = sys.argv[1], int(sys.argv[2]), sys.argv[3]


def normalise(word):
    return "".join(character for character in word.lower() if character.isalnum())


wanted = [normalise(word) for word in query.split()]
wanted = [word for word in wanted if word]
if not wanted or scale < 1:
    sys.exit(1)

words = []
with open(path, encoding="utf-8", errors="replace") as handle:
    handle.readline()
    for line in handle:
        fields = line.rstrip("\n").split("\t")
        if len(fields) < 12 or fields[0] != "5":
            continue
        text = fields[11].strip()
        if not text:
            continue
        try:
            confidence = float(fields[10])
            left, top, width, height = (int(fields[index]) for index in (6, 7, 8, 9))
        except ValueError:
            continue
        if confidence < 10:
            continue
        words.append(((fields[1], fields[2], fields[3], fields[4]), normalise(text),
                      left, top, width, height))

for start in range(len(words) - len(wanted) + 1):
    window = words[start:start + len(wanted)]
    if [word[1] for word in window] != wanted:
        continue
    if len({word[0] for word in window}) != 1:
        continue
    left = min(word[2] for word in window)
    top = min(word[3] for word in window)
    right = max(word[2] + word[4] for word in window)
    bottom = max(word[3] + word[5] for word in window)
    print((left + right) // 2 // scale, (top + bottom) // 2 // scale)
    sys.exit(0)
sys.exit(1)
'

gui_dir() {
    local dir=${SPACED_GUI_DIR:-$GUI_TMP_DIR}
    if [ -z "$dir" ]; then
        dir=$(dirname "${SPACED_VM_QMP_SOCKET:-$GUI_QMP}")
    fi
    printf '%s\n' "$dir"
}

gui_ssh() {
    SSHPASS="${SPACED_LIVE_ROOT_PASSWORD:-$GUI_ROOT_PASSWORD}" sshpass -e ssh \
        -p "${SPACED_VM_SSH_PORT:-$GUI_SSH_PORT}" \
        -o ConnectTimeout=10 -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null root@127.0.0.1 "$@"
}

# Run a command in the live desktop session (X display :0 belongs to "user").
gui_x() {
    local command
    printf -v command 'DISPLAY=:0 XAUTHORITY=/home/user/.Xauthority %s' "$(printf '%q ' "$@")"
    gui_ssh "su - user -c $(printf '%q' "$command")"
}

gui_shot() {
    local png=${1:-}
    if [ -z "$png" ]; then
        echo "gui_shot: usage gui_shot FILE.png" >&2
        return 2
    fi
    local qmp=${SPACED_VM_QMP_SOCKET:-$GUI_QMP}
    if [ ! -S "$qmp" ]; then
        echo "gui_shot: no QMP socket: $qmp" >&2
        return 2
    fi
    mkdir -p "$(dirname "$png")" || return 2
    python3 - "$qmp" "$png.ppm" <<'PY' || return 1
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
    python3 -c "$GUI_SHOT_PY" "$png.ppm" "$png" "$png-invert.png" \
        "${SPACED_GUI_SCALE:-$GUI_SCALE}" || return 1
    printf '%s\n' "$png"
}

# OCR one PNG: plain image first, inverted image when it yields nothing usable.
gui_ocr() {
    local png=${1:-}
    [ -n "$png" ] || return 2
    local text
    text=$(tesseract "$png" - --psm 11 2>/dev/null)
    if [ "$(printf '%s\n' "$text" | wc -w)" -lt 3 ] && [ -f "$png-invert.png" ]; then
        local inverted
        inverted=$(tesseract "$png-invert.png" - --psm 11 2>/dev/null)
        if [ "$(printf '%s\n' "$inverted" | wc -w)" -gt "$(printf '%s\n' "$text" | wc -w)" ]; then
            text=$inverted
        fi
    fi
    printf '%s\n' "$text"
}

gui_text() {
    local png
    png=$(gui_shot "$(gui_dir)/screen.png") || return 1
    gui_ocr "$png"
}

# Print the TSV word boxes of the current screen (debugging aid for gui_find).
gui_tsv() {
    local png
    png=$(gui_shot "$(gui_dir)/find.png") || return 1
    local tsv
    for image in "$png" "$png-invert.png"; do
        [ -f "$image" ] || continue
        tsv=$(tesseract "$image" - --psm 11 tsv 2>/dev/null)
        if [ "$(printf '%s\n' "$tsv" | grep -c '^5' | tr -d '\n')" != "0" ]; then
            printf '%s\n' "$tsv"
            return 0
        fi
    done
    return 1
}

gui_find() {
    local query=${1:-}
    if [ -z "$query" ]; then
        echo "gui_find: usage gui_find \"words\"" >&2
        return 2
    fi
    local png
    png=$(gui_shot "$(gui_dir)/find.png") || return 1
    local image
    for image in "$png" "$png-invert.png"; do
        [ -f "$image" ] || continue
        tesseract "$image" "$image" --psm 11 tsv 2>/dev/null || continue
        if python3 -c "$GUI_FIND_PY" "$query" "${SPACED_GUI_SCALE:-$GUI_SCALE}" \
                "$image.tsv" 2>/dev/null; then
            return 0
        fi
    done
    echo "gui_find: not on screen: $query" >&2
    return 1
}

gui_click_xy() {
    local x=${1:-} y=${2:-}
    if [[ ! "$x" =~ ^[0-9]+$ ]] || [[ ! "$y" =~ ^[0-9]+$ ]]; then
        echo "gui_click_xy: usage gui_click_xy X Y (screen pixels)" >&2
        return 2
    fi
    gui_x xdotool mousemove "$x" "$y" click 1
}

gui_click() {
    local query=${1:-}
    local xy x y
    if ! xy=$(gui_find "$query"); then
        echo "gui_click: no OCR match for: $query" >&2
        return 1
    fi
    read -r x y <<< "$xy"
    echo "gui_click: '$query' at $x,$y" >&2
    gui_click_xy "$x" "$y"
}

gui_type() {
    local text=${1:-}
    if [ -z "$text" ]; then
        echo "gui_type: usage gui_type \"text\"" >&2
        return 2
    fi
    gui_x xdotool type --delay 45 -- "$text"
}

gui_key() {
    local key=${1:-}
    if [ -z "$key" ]; then
        echo "gui_key: usage gui_key KEY" >&2
        return 2
    fi
    gui_x xdotool key "$key"
}

gui_wait() {
    local query=${1:-} timeout=${2:-60}
    if [ -z "$query" ] || [[ ! "$timeout" =~ ^[0-9]+$ ]]; then
        echo "gui_wait: usage gui_wait \"words\" SECONDS" >&2
        return 2
    fi
    local started=$SECONDS
    while (( SECONDS - started < timeout )); do
        if gui_find "$query" >/dev/null 2>&1; then
            echo "gui_wait: '$query' visible after $((SECONDS - started))s" >&2
            return 0
        fi
        sleep 3
    done
    echo "gui_wait: '$query' not visible within ${timeout}s" >&2
    return 1
}
