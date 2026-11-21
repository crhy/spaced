#!/bin/bash
# Issue #419 release gate: two live Spaced machines must share and copy a file
# across an isolated LAN. No host Samba service or outside network is involved.
set -euo pipefail

usage() {
    cat >&2 <<'EOF'
Usage: samba-network-gate.sh ISO

Boot two copies of the candidate ISO in KVM, connect them to an isolated QEMU
LAN, create a guest-writable Samba share on the first live machine, and prove
that smbclient and Caja's GVfs path on the second machine can copy files both
ways. Exit codes: 0 = PASS, 1 = regression, 2 = could not run.
EOF
}

ISO=${1:-}
if [ -z "$ISO" ]; then usage; exit 2; fi
if [ ! -f "$ISO" ]; then echo "ISO not found: $ISO" >&2; exit 2; fi
ISO=$(cd "$(dirname "$ISO")" && pwd)/${ISO##*/}

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd "$SCRIPT_DIR/../../.." && pwd)
NETWORK_TEST=$PROJECT_ROOT/scripts/tests/samba-network-test.sh
SERVER_SSH_PORT=${SPACED_SAMBA_SERVER_SSH_PORT:-2235}
CLIENT_SSH_PORT=${SPACED_SAMBA_CLIENT_SSH_PORT:-2236}
LAN_PORT=${SPACED_SAMBA_LAN_PORT:-22760}
RAM=${SPACED_SAMBA_VM_RAM:-2048}
CPUS=${SPACED_SAMBA_VM_CPUS:-2}
BOOT_TIMEOUT=${SPACED_ISO_BOOT_TIMEOUT:-360}
POLL=${SPACED_VM_POLL:-5}
ROOT_PASSWORD=${SPACED_LIVE_ROOT_PASSWORD:-spaced}
ISO_NAME=${ISO##*/}
ISO_NAME=${ISO_NAME%.iso}
OUT=${SPACED_SAMBA_GATE_DIR:-$PROJECT_ROOT/build/vm-tests/samba/$ISO_NAME}

for value in "$SERVER_SSH_PORT" "$CLIENT_SSH_PORT" "$LAN_PORT" "$RAM" "$CPUS" "$BOOT_TIMEOUT" "$POLL"; do
    [[ "$value" =~ ^[0-9]+$ ]] || { echo "Invalid numeric VM setting: $value" >&2; exit 2; }
done
for tool in qemu-system-x86_64 sshpass ssh; do
    command -v "$tool" >/dev/null || { echo "$tool is required for the Samba network gate" >&2; exit 2; }
done
if [ ! -e /dev/kvm ]; then
    echo "The Samba network gate needs KVM (/dev/kvm) to boot two live desktops" >&2
    exit 2
fi
if [ ! -f "$NETWORK_TEST" ]; then
    echo "Samba network test is missing: $NETWORK_TEST" >&2
    exit 2
fi

mkdir -p "$OUT"
OUT=$(cd "$OUT" && pwd)
rm -f "$OUT"/*.log
SERVER_PID=''
CLIENT_PID=''

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

echo "Starting two live Spaced machines for the Samba release gate"
qemu-system-x86_64 -enable-kvm -cpu host -m "$RAM" -smp "$CPUS" \
    -vga std -display none -snapshot -boot order=d -cdrom "$ISO" \
    -netdev "user,id=wan,hostfwd=tcp:127.0.0.1:$SERVER_SSH_PORT-:22" \
    -device virtio-net-pci,netdev=wan \
    -netdev "socket,id=lan,listen=127.0.0.1:$LAN_PORT" \
    -device virtio-net-pci,netdev=lan,mac=52:54:00:76:00:10 \
    -serial "file:$OUT/server-serial.log" >"$OUT/server-qemu.log" 2>&1 &
SERVER_PID=$!

wait_for_lan_listener

qemu-system-x86_64 -enable-kvm -cpu host -m "$RAM" -smp "$CPUS" \
    -vga std -display none -snapshot -boot order=d -cdrom "$ISO" \
    -netdev "user,id=wan,hostfwd=tcp:127.0.0.1:$CLIENT_SSH_PORT-:22" \
    -device virtio-net-pci,netdev=wan \
    -netdev "socket,id=lan,connect=127.0.0.1:$LAN_PORT" \
    -device virtio-net-pci,netdev=lan,mac=52:54:00:76:00:11 \
    -serial "file:$OUT/client-serial.log" >"$OUT/client-qemu.log" 2>&1 &
CLIENT_PID=$!

wait_for_desktop server "$SERVER_SSH_PORT" "$SERVER_PID"
wait_for_desktop client "$CLIENT_SSH_PORT" "$CLIENT_PID"

# Install the exact repository test on both live machines.
guest_ssh "$SERVER_SSH_PORT" 'tee /tmp/samba-network-test.sh >/dev/null && chmod 0755 /tmp/samba-network-test.sh' < "$NETWORK_TEST"
guest_ssh "$CLIENT_SSH_PORT" 'tee /tmp/samba-network-test.sh >/dev/null && chmod 0755 /tmp/samba-network-test.sh' < "$NETWORK_TEST"

configure_lan() {
    local port=$1 mac=$2 address=$3 hostname=$4
    guest_ssh "$port" "
iface=\$(for path in /sys/class/net/*/address; do
    [ \"\$(cat \"\$path\")\" = '$mac' ] && basename \"\$(dirname \"\$path\")\" && break
done)
test -n \"\$iface\"
# NetworkManager also manages this NIC and flushes hand-added addresses when its own profile activates
# (RC3 run: the server lost 192.168.76.10). The isolated test LAN is ours: take it away from NM first.
command -v nmcli >/dev/null && nmcli device set \"\$iface\" managed no 2>/dev/null || true
sleep 1
ip link set \"\$iface\" up
ip addr flush dev \"\$iface\"
ip addr add '$address/24' dev \"\$iface\"
printf '%s\\n' '$hostname' > /etc/hostname
hostname '$hostname'
printf '%s %s\\n' '$address' '$hostname' '$hostname.local' >> /etc/hosts
sleep 3
ip -4 addr show dev \"\$iface\" | grep -q '$address/' || { echo 'LAN address $address did not stick' >&2; exit 1; }
"
}
configure_lan "$SERVER_SSH_PORT" 52:54:00:76:00:10 192.168.76.10 spaced-share
configure_lan "$CLIENT_SSH_PORT" 52:54:00:76:00:11 192.168.76.11 spaced-client

# Reannounce both distinct machine identities after the isolated interface
# appears, then exercise the same user-facing share path as physical machines.
guest_ssh "$SERVER_SSH_PORT" '/etc/init.d/smbd restart; /etc/init.d/avahi-daemon restart; /etc/init.d/spaced-wsdd restart'
guest_ssh "$CLIENT_SSH_PORT" '/etc/init.d/smbd restart; /etc/init.d/avahi-daemon restart; /etc/init.d/spaced-wsdd restart'
run_as_live_user "$SERVER_SSH_PORT" bash /tmp/samba-network-test.sh local | tee "$OUT/server-local.log"
run_as_live_user "$SERVER_SSH_PORT" bash /tmp/samba-network-test.sh serve | tee "$OUT/server-serve.log"
run_as_live_user "$CLIENT_SSH_PORT" bash /tmp/samba-network-test.sh local | tee "$OUT/client-local.log"
run_as_live_user "$CLIENT_SSH_PORT" env SPACED_REQUIRE_GVFS_GUEST=1 SPACED_REQUIRE_NETWORK_BROWSE=1 \
    SPACED_EXPECT_BROWSE_NAME=SPACED-SHARE \
    bash /tmp/samba-network-test.sh peer 192.168.76.10 SpacedTest | tee "$OUT/client-peer.log"

echo "RESULT: PASS two live Spaced machines completed SMB and GVfs copy round trips"
echo "Artifacts: $OUT"
