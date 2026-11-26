#!/bin/bash
# Issues #419, #432, and #435 release gate: two live Spaced machines must share
# files and discover/deliver a print job across an isolated LAN. No host Samba,
# CUPS, or outside network service is involved.
set -euo pipefail

usage() {
    cat >&2 <<'EOF'
Usage: network-services-gate.sh ISO [SIGNED_APT_REPOSITORY]

Boot two copies of the candidate ISO, connect them to an isolated QEMU
LAN, and prove that NetworkManager recovers Samba/WSDD discovery, smbclient and
Caja copy files both ways, and CUPS discovers and uses an IPP Everywhere
printer. When a repository is supplied, upgrade both live systems from that
exact signed candidate before testing. Exit codes: 0 = PASS, 1 = regression,
2 = could not run.
EOF
}

ISO=${1:-}
REPO_DIR=${2:-}
if [ -z "$ISO" ]; then usage; exit 2; fi
if [ ! -f "$ISO" ]; then echo "ISO not found: $ISO" >&2; exit 2; fi
ISO=$(cd "$(dirname "$ISO")" && pwd)/${ISO##*/}
if [ -n "$REPO_DIR" ]; then
    [ -d "$REPO_DIR" ] || { echo "APT repository not found: $REPO_DIR" >&2; exit 2; }
    REPO_DIR=$(cd "$REPO_DIR" && pwd)
fi

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd "$SCRIPT_DIR/../../.." && pwd)
NETWORK_TEST=$PROJECT_ROOT/scripts/tests/samba-network-test.sh
PRINTING_TEST=$PROJECT_ROOT/scripts/tests/printing-network-test.sh
SERVER_SSH_PORT=${SPACED_NETWORK_SERVER_SSH_PORT:-${SPACED_SAMBA_SERVER_SSH_PORT:-2235}}
CLIENT_SSH_PORT=${SPACED_NETWORK_CLIENT_SSH_PORT:-${SPACED_SAMBA_CLIENT_SSH_PORT:-2236}}
LAN_PORT=${SPACED_NETWORK_LAN_PORT:-${SPACED_SAMBA_LAN_PORT:-22760}}
RAM=${SPACED_NETWORK_VM_RAM:-${SPACED_SAMBA_VM_RAM:-2048}}
CPUS=${SPACED_NETWORK_VM_CPUS:-${SPACED_SAMBA_VM_CPUS:-2}}
ACCEL=${SPACED_QEMU_ACCEL:-kvm}
BOOT_TIMEOUT=${SPACED_ISO_BOOT_TIMEOUT:-${SPACED_ISO_SMOKE_TIMEOUT:-360}}
POLL=${SPACED_VM_POLL:-5}
ROOT_PASSWORD=${SPACED_LIVE_ROOT_PASSWORD:-spaced}
ISO_NAME=${ISO##*/}
ISO_NAME=${ISO_NAME%.iso}
OUT=${SPACED_NETWORK_GATE_DIR:-${SPACED_SAMBA_GATE_DIR:-$PROJECT_ROOT/build/test-artifacts/network-services/$ISO_NAME}}
REPO_SUITE=${SPACED_APT_SUITE:-spaced}
REPO_HTTP_PORT=${SPACED_NETWORK_REPO_HTTP_PORT:-22761}
UPGRADE_TIMEOUT=${SPACED_NETWORK_UPGRADE_TIMEOUT:-1800}

for value in "$SERVER_SSH_PORT" "$CLIENT_SSH_PORT" "$LAN_PORT" "$RAM" "$CPUS" "$BOOT_TIMEOUT" "$POLL" "$REPO_HTTP_PORT" "$UPGRADE_TIMEOUT"; do
    [[ "$value" =~ ^[0-9]+$ ]] || { echo "Invalid numeric VM setting: $value" >&2; exit 2; }
done
case "$ACCEL" in
    kvm) QEMU_ACCEL_ARGS=(-enable-kvm -cpu host) ;;
    tcg) QEMU_ACCEL_ARGS=(-accel "tcg,thread=multi" -cpu max) ;;
    *) echo "SPACED_QEMU_ACCEL must be kvm or tcg (got $ACCEL)" >&2; exit 2 ;;
esac
for tool in qemu-system-x86_64 sshpass ssh; do
    command -v "$tool" >/dev/null || { echo "$tool is required for the network services gate" >&2; exit 2; }
done
if [ -n "$REPO_DIR" ]; then
    command -v python3 >/dev/null || { echo "python3 is required to serve the candidate repository" >&2; exit 2; }
    [ -s "$REPO_DIR/dists/$REPO_SUITE/InRelease" ] || { echo "Missing signed InRelease for suite $REPO_SUITE" >&2; exit 2; }
    [ -s "$REPO_DIR/dists/$REPO_SUITE/main/binary-amd64/Packages" ] || { echo "Missing amd64 Packages index for suite $REPO_SUITE" >&2; exit 2; }
fi
if [ ! -f "$NETWORK_TEST" ]; then
    echo "Samba network test is missing: $NETWORK_TEST" >&2
    exit 2
fi
if [ ! -f "$PRINTING_TEST" ]; then
    echo "Printing network test is missing: $PRINTING_TEST" >&2
    exit 2
fi

if [ "$ACCEL" = kvm ] && [ ! -e /dev/kvm ]; then
    echo "SPACED_QEMU_ACCEL=kvm but /dev/kvm is unavailable" >&2
    exit 2
fi

mkdir -p "$OUT"
OUT=$(cd "$OUT" && pwd)
rm -f "$OUT"/*.log
SERVER_PID=''
CLIENT_PID=''
HTTP_PID=''

stop_vm() {
    local pid=$1
    [ -n "$pid" ] || return 0
    if kill -0 "$pid" 2>/dev/null; then
        kill "$pid" 2>/dev/null || true
        for _ in {1..20}; do
            kill -0 "$pid" 2>/dev/null || break
            sleep 0.2
        done
        kill -KILL "$pid" 2>/dev/null || true
    fi
    wait "$pid" 2>/dev/null || true
}
cleanup() {
    stop_vm "$CLIENT_PID"
    stop_vm "$SERVER_PID"
    if [ -n "$HTTP_PID" ]; then
        kill "$HTTP_PID" 2>/dev/null || true
        wait "$HTTP_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

guest_ssh() {
    local port=$1
    shift
    SSHPASS="$ROOT_PASSWORD" sshpass -e ssh -p "$port" \
        -o ConnectTimeout=10 -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null root@127.0.0.1 "$@"
}

wait_for_desktop() {
    local name=$1 port=$2 pid=$3 started=$SECONDS
    while (( SECONDS - started < BOOT_TIMEOUT )); do
        if ! kill -0 "$pid" 2>/dev/null; then
            echo "$name VM exited before its desktop was ready; see $OUT/$name-qemu.log" >&2
            return 1
        fi
        if guest_ssh "$port" \
            'pgrep -x mate-panel >/dev/null && pgrep -x caja >/dev/null && pgrep -x compiz >/dev/null' \
            >/dev/null 2>&1; then
            echo "$name live desktop ready after $((SECONDS - started))s"
            return 0
        fi
        sleep "$POLL"
    done
    echo "$name live desktop did not start within ${BOOT_TIMEOUT}s" >&2
    return 1
}

upgrade_guest() {
    local name=$1 port=$2 repo_url=$3
    guest_ssh "$port" bash -s -- "$repo_url" "$REPO_SUITE" "$UPGRADE_TIMEOUT" <<'UPGRADE'
set -euo pipefail
repo_url=$1
suite=$2
upgrade_timeout=$3

# Replace only the signed Spaced source. Devuan remains available for package
# dependencies, while all Spaced packages must come from the supplied candidate.
python3 - "$repo_url" "$suite" <<'PY'
from pathlib import Path
import re
import sys

repo_url, suite = sys.argv[1:]
paths = [Path("/etc/apt/sources.list"), *Path("/etc/apt/sources.list.d").glob("*.list")]
matches = []
for path in paths:
    if not path.exists():
        continue
    lines = path.read_text().splitlines()
    changed = False
    for index, line in enumerate(lines):
        if re.match(r"^\s*deb\s+\[.*signed-by=.*spaced.*\]", line, re.I):
            matches.append((path, index))
            options = re.match(r"^\s*deb\s+(\[[^]]+\])", line).group(1)
            lines[index] = f"deb {options} {repo_url} {suite} main"
            changed = True
    if changed:
        path.write_text("\n".join(lines) + "\n")
if len(matches) != 1:
    raise SystemExit(f"expected exactly one signed Spaced APT source, found {len(matches)}")
PY

apt-get -o APT::Update::Error-Mode=any update
if [ -x /usr/lib/spaced-linux/spaced-update-helper ]; then
    timeout "$upgrade_timeout" /usr/lib/spaced-linux/spaced-update-helper all
else
    DEBIAN_FRONTEND=noninteractive timeout "$upgrade_timeout" \
        apt-get -y -o Dpkg::Options::=--force-confold full-upgrade
fi
dpkg --configure --pending
test -z "$(dpkg --audit)"
apt-get check
if apt-get -s full-upgrade | grep -q '^Inst spaced-'; then
    echo "Spaced packages remain upgradeable after candidate upgrade" >&2
    exit 1
fi
UPGRADE
    echo "$name upgraded from the signed candidate repository"
}

wait_for_lan_listener() {
    local port_hex started=$SECONDS
    printf -v port_hex '%04X' "$LAN_PORT"
    while (( SECONDS - started < 15 )); do
        if ! kill -0 "$SERVER_PID" 2>/dev/null; then
            echo "Server VM exited before opening its isolated LAN; see $OUT/server-qemu.log" >&2
            return 1
        fi
        if awk -v port="$port_hex" '
            $4 == "0A" && substr($2, length($2) - 4) == ":" port { found = 1 }
            END { exit !found }
        ' /proc/net/tcp /proc/net/tcp6 2>/dev/null; then
            return 0
        fi
        sleep 0.1
    done
    echo "Server VM did not open isolated LAN port $LAN_PORT; see $OUT/server-qemu.log" >&2
    return 1
}

run_as_live_user() {
    local port=$1
    shift
    local session_bus
    session_bus=$(guest_ssh "$port" \
        'pid=$(pgrep -o -u user mate-panel); tr "\0" "\n" < "/proc/$pid/environ" | sed -n "s/^DBUS_SESSION_BUS_ADDRESS=//p"')
    if [ -z "$session_bus" ]; then
        echo "Could not find the MATE session D-Bus address on SSH port $port" >&2
        return 1
    fi
    guest_ssh "$port" runuser -u user -- env HOME=/home/user USER=user LOGNAME=user \
        DISPLAY=:0 XAUTHORITY=/home/user/.Xauthority XDG_RUNTIME_DIR=/run/user/1000 \
        DBUS_SESSION_BUS_ADDRESS="$session_bus" "$@"
}

if [ -n "$REPO_DIR" ]; then
    python3 -m http.server "$REPO_HTTP_PORT" --bind 0.0.0.0 --directory "$REPO_DIR" \
        >"$OUT/repository-http.log" 2>&1 &
    HTTP_PID=$!
    HTTP_READY=0
    for _ in {1..50}; do
        kill -0 "$HTTP_PID" 2>/dev/null || {
            echo "Candidate repository HTTP server exited" >&2
            exit 2
        }
        if (exec 3<>"/dev/tcp/127.0.0.1/$REPO_HTTP_PORT") 2>/dev/null; then
            exec 3>&-
            HTTP_READY=1
            break
        fi
        sleep 0.1
    done
    [ "$HTTP_READY" = 1 ] || {
        echo "Candidate repository HTTP server did not become ready" >&2
        exit 2
    }
    REPO_URL="http://10.0.2.2:$REPO_HTTP_PORT"
    echo "Candidate repository available to both guests at $REPO_URL"
fi

echo "Starting two live Spaced machines for the network services release gate ($ACCEL)"
qemu-system-x86_64 "${QEMU_ACCEL_ARGS[@]}" -m "$RAM" -smp "$CPUS" \
    -vga std -display none -snapshot -boot order=d -cdrom "$ISO" \
    -netdev "user,id=wan,hostfwd=tcp:127.0.0.1:$SERVER_SSH_PORT-:22" \
    -device virtio-net-pci,netdev=wan \
    -netdev "socket,id=lan,listen=127.0.0.1:$LAN_PORT" \
    -device virtio-net-pci,netdev=lan,mac=52:54:00:76:00:10 \
    -serial "file:$OUT/server-serial.log" >"$OUT/server-qemu.log" 2>&1 &
SERVER_PID=$!

wait_for_lan_listener

qemu-system-x86_64 "${QEMU_ACCEL_ARGS[@]}" -m "$RAM" -smp "$CPUS" \
    -vga std -display none -snapshot -boot order=d -cdrom "$ISO" \
    -netdev "user,id=wan,hostfwd=tcp:127.0.0.1:$CLIENT_SSH_PORT-:22" \
    -device virtio-net-pci,netdev=wan \
    -netdev "socket,id=lan,connect=127.0.0.1:$LAN_PORT" \
    -device virtio-net-pci,netdev=lan,mac=52:54:00:76:00:11 \
    -serial "file:$OUT/client-serial.log" >"$OUT/client-qemu.log" 2>&1 &
CLIENT_PID=$!

wait_for_desktop server "$SERVER_SSH_PORT" "$SERVER_PID"
wait_for_desktop client "$CLIENT_SSH_PORT" "$CLIENT_PID"

if [ -n "$REPO_DIR" ]; then
    upgrade_guest server "$SERVER_SSH_PORT" "$REPO_URL" | tee "$OUT/server-upgrade.log"
    upgrade_guest client "$CLIENT_SSH_PORT" "$REPO_URL" | tee "$OUT/client-upgrade.log"
fi

# Install the exact repository tests on both live machines.
guest_ssh "$SERVER_SSH_PORT" 'tee /tmp/samba-network-test.sh >/dev/null && chmod 0755 /tmp/samba-network-test.sh' < "$NETWORK_TEST"
guest_ssh "$CLIENT_SSH_PORT" 'tee /tmp/samba-network-test.sh >/dev/null && chmod 0755 /tmp/samba-network-test.sh' < "$NETWORK_TEST"
guest_ssh "$SERVER_SSH_PORT" 'tee /tmp/printing-network-test.sh >/dev/null && chmod 0755 /tmp/printing-network-test.sh' < "$PRINTING_TEST"
guest_ssh "$CLIENT_SSH_PORT" 'tee /tmp/printing-network-test.sh >/dev/null && chmod 0755 /tmp/printing-network-test.sh' < "$PRINTING_TEST"

configure_lan() {
    local port=$1 mac=$2 address=$3 hostname=$4
    guest_ssh "$port" "
iface=\$(for path in /sys/class/net/*/address; do
    [ \"\$(cat \"\$path\")\" = '$mac' ] && basename \"\$(dirname \"\$path\")\" && break
done)
test -n \"\$iface\"
command -v nmcli >/dev/null
printf '%s\\n' '$hostname' > /etc/hostname
hostname '$hostname'
# Stop discovery before activating the profile. The NetworkManager dispatcher
# must recover both services; an explicit restart here would mask issue #432.
/etc/init.d/smbd stop
/etc/init.d/spaced-wsdd stop
nmcli connection delete spaced-test-lan >/dev/null 2>&1 || true
nmcli device set \"\$iface\" managed yes
nmcli connection add type ethernet ifname \"\$iface\" con-name spaced-test-lan \
    connection.autoconnect no ipv4.method manual ipv4.addresses '$address/24' \
    ipv4.never-default yes ipv6.method disabled
nmcli connection up spaced-test-lan
ip -4 addr show dev \"\$iface\" | grep -q '$address/' || { echo 'LAN address $address did not stick' >&2; exit 1; }
"
}
configure_lan "$SERVER_SSH_PORT" 52:54:00:76:00:10 192.168.76.10 spaced-share
configure_lan "$CLIENT_SSH_PORT" 52:54:00:76:00:11 192.168.76.11 spaced-client

# Name resolution is deterministic even if Avahi retains the live image's
# original hostname. IPP service discovery still has to cross the isolated LAN.
for port in "$SERVER_SSH_PORT" "$CLIENT_SSH_PORT"; do
    guest_ssh "$port" "printf '%s\\n' \
        '192.168.76.10 spaced-share spaced-share.local' \
        '192.168.76.11 spaced-client spaced-client.local' >> /etc/hosts"
done

wait_for_guest_service() {
    local port=$1 service=$2 started=$SECONDS
    while (( SECONDS - started < 30 )); do
        if guest_ssh "$port" "/etc/init.d/$service status" >/dev/null 2>&1; then
            return 0
        fi
        sleep 1
    done
    echo "$service was not recovered by NetworkManager on SSH port $port" >&2
    return 1
}

# This is an assertion, not setup: only the dispatcher may have restarted them.
for port in "$SERVER_SSH_PORT" "$CLIENT_SSH_PORT"; do
    wait_for_guest_service "$port" smbd
    wait_for_guest_service "$port" spaced-wsdd
done

# Exercise the same user-facing share and print paths as physical machines.
run_as_live_user "$SERVER_SSH_PORT" bash /tmp/samba-network-test.sh local | tee "$OUT/server-local.log"
run_as_live_user "$SERVER_SSH_PORT" bash /tmp/samba-network-test.sh serve | tee "$OUT/server-serve.log"
run_as_live_user "$CLIENT_SSH_PORT" bash /tmp/samba-network-test.sh local | tee "$OUT/client-local.log"
run_as_live_user "$CLIENT_SSH_PORT" env SPACED_REQUIRE_GVFS_GUEST=1 SPACED_REQUIRE_NETWORK_BROWSE=1 \
    SPACED_EXPECT_BROWSE_NAME=SPACED-SHARE \
    bash /tmp/samba-network-test.sh peer 192.168.76.10 SpacedTest | tee "$OUT/client-peer.log"

guest_ssh "$SERVER_SSH_PORT" bash /tmp/printing-network-test.sh serve | tee "$OUT/server-print-serve.log"
guest_ssh "$CLIENT_SSH_PORT" bash /tmp/printing-network-test.sh peer | tee "$OUT/client-print-peer.log"
guest_ssh "$SERVER_SSH_PORT" bash /tmp/printing-network-test.sh verify | tee "$OUT/server-print-verify.log"
guest_ssh "$SERVER_SSH_PORT" bash /tmp/printing-network-test.sh stop | tee "$OUT/server-print-stop.log"

echo "RESULT: PASS two live Spaced machines completed SMB/GVfs copy and IPP print round trips"
echo "Artifacts: $OUT"
