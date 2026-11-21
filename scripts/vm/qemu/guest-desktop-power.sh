#!/bin/bash
# Test-only: run over SSH as the live user in an explicitly disposable VM.
# The actual power request is made by mate-session after its dialog receives
# a keyboard activation, not by this SSH caller or a privileged fallback.
set -euo pipefail

[[ ${1:-} == --disposable-live-vm ]] || exit 2
ACTION=${2:-}
case "$ACTION" in
    Reboot) KEY=alt+r ;;
    PowerOff) KEY=alt+s ;;
    *) exit 2 ;;
esac
[[ $(id -un) == user && $(id -u) != 0 ]] || exit 2
grep -qw boot=live /proc/cmdline || exit 2
grep -qw hypervisor /proc/cpuinfo || exit 2
for tool in xdotool xprop mate-session-save gsettings timeout gdbus; do
    command -v "$tool" >/dev/null || exit 2
done
# SSH and logind can be ready before MATE has entered its Running phase.
# Wait for that phase without repeatedly opening a power dialog.
READY=no
for _ in {1..120}; do
    SESSION_PID=$(pgrep -u "$(id -u)" -x mate-session || true)
    if [[ ! "$SESSION_PID" =~ ^[0-9]+$ ]] || [[ ! -r /proc/$SESSION_PID/environ ]]; then
        sleep 1
        continue
    fi
    # Use the existing graphical session's bus, never an SSH-created bus.
    unset DBUS_SESSION_BUS_ADDRESS DISPLAY XAUTHORITY LC_ALL LC_MESSAGES
    while IFS= read -r -d '' entry; do
        case "$entry" in
            DBUS_SESSION_BUS_ADDRESS=*|DISPLAY=*|XAUTHORITY=*|LANG=*|LC_ALL=*|LC_MESSAGES=*)
                export "$entry" ;;
        esac
    done < "/proc/$SESSION_PID/environ"
    if [[ -n ${DISPLAY:-} && -n ${DBUS_SESSION_BUS_ADDRESS:-} ]] &&
        timeout 2 gdbus call --session --dest org.gnome.SessionManager \
            --object-path /org/gnome/SessionManager \
            --method org.gnome.SessionManager.IsSessionRunning 2>/dev/null | grep -qx '(true,)'; then
        READY=yes
        break
    fi
    sleep 1
done
[[ "$READY" = yes ]] || { echo 'MATE session never reached Running'; exit 1; }
LOCALE=${LC_ALL:-${LC_MESSAGES:-${LANG:-C}}}
case "$LOCALE" in en*|C|C.*|POSIX) ;; *) echo 'English dialog mnemonics required'; exit 2 ;; esac

# A missing/disabled button must not let the dialog's countdown silently shut
# down the VM instead. Restore the setting; this dialog already read it.
OLD_TIMEOUT=$(gsettings get org.mate.session logout-timeout)
trap 'gsettings set org.mate.session logout-timeout "$OLD_TIMEOUT" || true' EXIT
gsettings set org.mate.session logout-timeout 0
timeout 10 mate-session-save --shutdown-dialog
DIALOG=''
for _ in {1..30}; do
    DIALOG=$(xdotool search --onlyvisible --pid "$SESSION_PID" --class '^Mate-session$' || true)
    [[ "$DIALOG" =~ ^[0-9]+$ ]] && break
    sleep 0.1
done
[[ "$DIALOG" =~ ^[0-9]+$ ]] || { echo 'No unique MATE shutdown dialog'; exit 1; }
xprop -id "$DIALOG" WM_CLASS _NET_WM_PID _NET_WM_WINDOW_TYPE
xprop -id "$DIALOG" _NET_WM_WINDOW_TYPE | grep -q _NET_WM_WINDOW_TYPE_DIALOG
gsettings set org.mate.session logout-timeout "$OLD_TIMEOUT"
trap - EXIT
timeout 10 xdotool windowactivate --sync "$DIALOG"
echo "DESKTOP_ACTION_SENT: $ACTION via MATE dialog $DIALOG (session PID $SESSION_PID)"
# The X connection may disappear while the key is being delivered. The host
# harness must still require a new boot ID (or QEMU exit for PowerOff).
xdotool key --clearmodifiers "$KEY" || true
