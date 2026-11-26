#!/bin/bash
# End-to-end network-printing check used by the two-live-machine release gate.
set -euo pipefail

SERVICE_NAME=${SPACED_PRINT_SERVICE_NAME:-Spaced Network Printer}
QUEUE_NAME=${SPACED_PRINT_QUEUE_NAME:-Spaced_Network_Printer}
PRINT_PORT=${SPACED_PRINT_PORT:-8631}
STATE_DIR=${SPACED_PRINT_STATE_DIR:-/tmp/spaced-network-printer}
PID_FILE=$STATE_DIR/ippeveprinter.pid
SPOOL_DIR=$STATE_DIR/spool
LOG_FILE=$STATE_DIR/ippeveprinter.log
TIMEOUT=${SPACED_PRINT_TIMEOUT:-60}

fail() {
    echo "FAIL: $*" >&2
    exit 1
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || fail "$1 is not installed"
}

service_running() {
    local service=$1
    [ -x "/etc/init.d/$service" ] || fail "$service has no sysvinit service"
    "/etc/init.d/$service" status >/dev/null 2>&1 || \
        fail "$service is not running"
}

wait_until() {
    local description=$1
    shift
    local started=$SECONDS
    until "$@"; do
        (( SECONDS - started < TIMEOUT )) || fail "timed out waiting for $description"
        sleep 1
    done
}

printer_visible() {
    ippfind -T 2 _ipp._tcp --literal-name "$SERVICE_NAME" --remote --quiet \
        >/dev/null 2>&1
}

queue_visible() {
    lpstat -e 2>/dev/null | grep -Fxq "$QUEUE_NAME"
}

queue_owned_by_cups_browsed() {
    [ -r /etc/cups/printers.conf ] || return 1
    awk -v queue="$QUEUE_NAME" '
        $0 == "<Printer " queue ">" || $0 == "<DefaultPrinter " queue ">" {
            in_queue = 1
            next
        }
        in_queue && /^<\/(Default)?Printer>$/ { exit found ? 0 : 1 }
        in_queue && /cups-browsed/ { found = 1 }
        END { if (!in_queue || !found) exit 1 }
    ' /etc/cups/printers.conf
}

document_delivered() {
    [ -n "$(find "$SPOOL_DIR" -type f -size +0c -print -quit 2>/dev/null)" ]
}

case "${1:-}" in
    serve)
        require_command ippeveprinter
        require_command ippfind
        service_running avahi-daemon
        install -d -m 0755 "$SPOOL_DIR"
        if [ -s "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
            fail "test printer is already running"
        fi
        rm -f "$PID_FILE" "$SPOOL_DIR"/*
        # Accept the formats a driverless CUPS client normally produces and
        # retain the received document so the server can prove real delivery.
        nohup ippeveprinter -k -d "$SPOOL_DIR" -p "$PRINT_PORT" \
            -f application/pdf,application/postscript,image/pwg-raster,image/urf \
            "$SERVICE_NAME" </dev/null >"$LOG_FILE" 2>&1 &
        echo $! > "$PID_FILE"
        sleep 1
        kill -0 "$(cat "$PID_FILE")" 2>/dev/null || {
            sed -n '1,120p' "$LOG_FILE" >&2 || true
            fail "ippeveprinter exited during startup"
        }
        echo "PASS: advertised IPP Everywhere test printer"
        ;;
    peer)
        require_command ippfind
        require_command lp
        require_command lpstat
        service_running cups
        service_running cups-browsed
        service_running avahi-daemon
        wait_until "remote IPP DNS-SD discovery" printer_visible
        wait_until "cups-browsed queue $QUEUE_NAME" queue_visible
        wait_until "a persistent cups-browsed queue" queue_owned_by_cups_browsed
        test_page=/usr/share/cups/data/default-testpage.pdf
        [ -r "$test_page" ] || test_page=/usr/share/cups/data/testprint
        [ -r "$test_page" ] || fail "CUPS test page is missing"
        job=$(lp -d "$QUEUE_NAME" -o job-sheets=none "$test_page")
        printf '%s\n' "$job"
        echo "PASS: discovered cups-browsed queue and submitted a print job"
        ;;
    verify)
        [ -s "$PID_FILE" ] || fail "test printer pid is missing"
        kill -0 "$(cat "$PID_FILE")" 2>/dev/null || fail "test printer stopped"
        wait_until "a delivered print document" document_delivered
        echo "PASS: server received a nonempty print document"
        ;;
    stop)
        if [ -s "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
            kill "$(cat "$PID_FILE")"
        fi
        rm -f "$PID_FILE"
        ;;
    *)
        echo "Usage: $0 {serve|peer|verify|stop}" >&2
        exit 2
        ;;
esac
