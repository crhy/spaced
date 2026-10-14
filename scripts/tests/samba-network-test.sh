#!/bin/bash
# Windows/Samba file-sharing checks for real machines on a local network
# (issue #297). Run as the desktop user, not root; sudo is never used.
#
#   samba-network-test.sh local                 this machine can serve shares
#   samba-network-test.sh serve                 keep a SpacedTest share up
#   samba-network-test.sh serve --stop          remove it again
#   samba-network-test.sh peer HOST [SHARE] [-U USER]
#                                               reach another machine's share
#
# Every run appends to ~/spaced-samba-test-HOSTNAME.log; attach that file to
# the issue. Exit status is the number of FAIL results (0 means all passed).
set -uo pipefail

LOG="$HOME/spaced-samba-test-$(hostname).log"
SERVE_NAME=SpacedTest
SERVE_DIR="$HOME/SpacedShareTest"
fails=0 warns=0

say() { printf '%s\n' "$*" | tee -a "$LOG"; }
pass() { say "PASS  $*"; }
fail() { say "FAIL  $*"; fails=$((fails + 1)); }
warn() { say "WARN  $*"; warns=$((warns + 1)); }
info() { say "INFO  $*"; }
detail() { sed 's/^/      /' | tee -a "$LOG"; }
have() { command -v "$1" >/dev/null 2>&1; }

header() {
    say ""
    say "=== $1: $(date '+%F %T') on $(hostname) ==="
    info "$(. /etc/os-release && printf '%s' "$PRETTY_NAME")," \
        "spaced-meta $(dpkg-query -W -f='${Version}' spaced-meta 2>/dev/null || echo none)," \
        "samba $(dpkg-query -W -f='${Version}' samba 2>/dev/null || echo none)"
    info "addresses: $(hostname -I 2>/dev/null)"
}

# A file whose contents identify the writer, for round-trip comparisons.
payload() {
    printf 'Spaced Samba test from %s at %s\n' "$(hostname)" "$(date '+%F %T')" > "$1"
    head -c 1048576 /dev/urandom >> "$1"
}

# put, get back, compare, delete: proves write, read and delete permission.
round_trip() { # label service [smbclient options...]
    local label=$1 service=$2
    shift 2
    local work name out
    work=$(mktemp -d)
    name="spaced-test-$(hostname)-$$.bin"
    payload "$work/up"
    if ! out=$(cd "$work" && smbclient "$service" "$@" -c "put up $name; get $name down; rm $name" 2>&1); then
        fail "$label: put/get/delete on $service"
        printf '%s\n' "$out" | detail
    elif cmp -s "$work/up" "$work/down"; then
        pass "$label: wrote, read back identical 1 MiB file, deleted it on $service"
    else
        fail "$label: file read back from $service differs from what was written"
    fi
    rm -rf "$work"
}

check_local() {
    header "local"

    local package
    for package in samba smbclient caja-share wsdd avahi-daemon libnss-mdns gigolo; do
        if dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q 'ok installed'; then
            pass "package $package installed"
        else
            fail "package $package missing"
        fi
    done

    if /etc/init.d/smbd status >/dev/null 2>&1; then
        pass "smbd is running"
    else
        fail "smbd is not running (issue #297): sudo /etc/init.d/smbd start"
    fi
    local runlevel link boot=no
    runlevel=$(runlevel 2>/dev/null | awk '{print $2}')
    for link in "/etc/rc${runlevel:-2}.d/"S[0-9][0-9]smbd; do
        [ -e "$link" ] && boot=yes
    done
    if [ "$boot" = yes ]; then
        pass "smbd starts at boot (runlevel ${runlevel:-2} link present)"
    else
        fail "smbd will not start at boot: $(echo /etc/rc[2-5].d/[SK][0-9][0-9]smbd)"
    fi
    if /etc/init.d/avahi-daemon status >/dev/null 2>&1; then
        pass "avahi-daemon is running"
    else
        fail "avahi-daemon is not running"
    fi
    info "nmbd (NetBIOS names, optional): $(/etc/init.d/nmbd status 2>&1 | head -1)"
    if pgrep -x wsdd >/dev/null || pgrep -f 'wsdd(\.py)? ' >/dev/null; then
        info "a wsdd process is running: $(pgrep -af wsdd | head -2 | tr '\n' ' ')"
    else
        warn "no wsdd announcer: Windows will not list this machine under Network (direct \\\\IP\\share still works)"
    fi

    if have ss; then
        if ss -Hltn 'sport = :445' | grep -q .; then
            pass "something listens on TCP 445: $(ss -Hltn 'sport = :445' | awk '{print $4}' | tr '\n' ' ')"
        else
            fail "nothing listens on TCP 445, so other computers get \"connection refused\""
        fi
    fi

    local params
    params=$(testparm -s 2>/dev/null)
    local max
    max=$(printf '%s\n' "$params" | awk -F= '/usershare max shares/ {gsub(/ /, "", $2); print $2}')
    if [ "${max:-0}" -gt 0 ] 2>/dev/null; then
        pass "usershare max shares = $max"
    else
        fail "user shares are disabled (usershare max shares is 0 or unset, issue #253)"
    fi
    printf '%s\n' "$params" | grep -Eiq 'usershare allow guests = (yes|true)' \
        && pass "usershare allow guests = yes" \
        || fail "guest user shares are not allowed, so Caja's Guest access option fails"
    info "testparm: $(printf '%s\n' "$params" | grep -Ei 'map to guest|server min protocol|server signing|interfaces|bind interfaces only' | sed 's/^[[:space:]]*//' | paste -sd ';' -)"

    if id -nG | tr ' ' '\n' | grep -qx sambashare; then
        pass "$(id -un) is in group sambashare"
    else
        fail "$(id -un) is not in group sambashare (log out and in after: sudo usermod -aG sambashare $(id -un))"
    fi
    if have pdbedit && pdbedit -L 2>/dev/null | grep -q "^$(id -un):"; then
        info "$(id -un) has a Samba password (authenticated access possible)"
    else
        warn "$(id -un) has no Samba password: Windows 11 refuses guest access, so it can only open this machine's shares after: sudo smbpasswd -a $(id -un)"
    fi

    local folders
    folders=$(XDG_CURRENT_DESKTOP=MATE gio mime inode/directory 2>/dev/null | head -1)
    if printf '%s' "$folders" | grep -q caja-folder-handler.desktop; then
        pass "folders open in Caja"
    else
        fail "folders do not open in Caja: $folders (issue #297, Gigolo opened VSCodium)"
    fi
    if [ -f "$HOME/.config/gigolo/config" ]; then
        info "Gigolo $(grep -E '^(file_manager|terminal)=' "$HOME/.config/gigolo/config" | paste -sd ' ' -)"
    fi

    if have iptables && iptables -S 2>/dev/null | grep -Eq -- '-j (DROP|REJECT)'; then
        warn "iptables has DROP/REJECT rules; check they allow TCP 445 and UDP 5353/3702"
    fi
    if have nft && nft list ruleset 2>/dev/null | grep -Eq '\b(drop|reject)\b'; then
        warn "nftables has drop/reject rules; check they allow TCP 445 and UDP 5353/3702"
    fi

    # Guests are mapped to nobody, which must traverse every parent of a
    # shared folder. HOME_MODE 0700 stops it at the home directory.
    if [ $(( 0$(stat -c %a "$HOME") & 01 )) -eq 1 ]; then
        pass "home $HOME (mode $(stat -c %a "$HOME")) lets guests reach shared folders inside it"
    else
        fail "home $HOME is mode $(stat -c %a "$HOME"): guests (Everyone) cannot reach any folder shared from inside it"
    fi

    # The same calls Caja's Sharing Options makes for "Everyone" access.
    local name dir out
    name="spacedcheck$$"
    dir=$(mktemp -d "$HOME/.spaced-samba-check.XXXXXX")
    chmod 0777 "$dir"
    if out=$(net usershare add "$name" "$dir" "Spaced check" Everyone:F guest_ok=y 2>&1); then
        pass "net usershare add with Everyone:F and guest access (Caja Sharing Options)"
        net usershare info "$name" 2>&1 | detail
        round_trip "guest on localhost" "//127.0.0.1/$name" -N
        local user_password=${SPACED_SMB_PASSWORD:-}
        if [ -n "$user_password" ]; then
            round_trip "user $(id -un) on localhost" "//127.0.0.1/$name" -U "$(id -un)%$user_password"
        else
            info "set SPACED_SMB_PASSWORD to also test authenticated access to this share"
        fi
        net usershare delete "$name" >/dev/null 2>&1 || warn "could not delete test share $name"
    else
        fail "net usershare add failed (this is the error Caja shows)"
        printf '%s\n' "$out" | detail
    fi
    rm -rf "$dir"
}

serve() {
    header "serve"
    if [ "${1:-}" = --stop ]; then
        net usershare delete "$SERVE_NAME" >/dev/null 2>&1 && pass "removed share $SERVE_NAME" \
            || info "share $SERVE_NAME was not present"
        info "test folder $SERVE_DIR kept; delete it by hand when done"
        return
    fi
    mkdir -p "$SERVE_DIR"
    chmod 0777 "$SERVE_DIR"
    printf 'Served by %s (%s) since %s\n' "$(hostname)" "$(hostname -I)" "$(date '+%F %T')" \
        > "$SERVE_DIR/README-$(hostname).txt"
    local out
    if out=$(net usershare add "$SERVE_NAME" "$SERVE_DIR" "Spaced network test" Everyone:F guest_ok=y 2>&1); then
        pass "sharing $SERVE_DIR as $SERVE_NAME (Everyone: full control, guests allowed)"
        local address
        for address in $(hostname -I); do
            case $address in *:*) continue ;; esac
            info "from Spaced:  smb://$address/$SERVE_NAME   or   $0 peer $address"
            info "from Windows: \\\\$address\\$SERVE_NAME"
        done
        info "by name: smb://$(hostname).local/$SERVE_NAME"
        info "stop with: $0 serve --stop"
    else
        fail "could not share $SERVE_DIR"
        printf '%s\n' "$out" | detail
    fi
}

check_peer() {
    local host=${1:?Usage: $0 peer HOST [SHARE] [-U USER]}
    shift
    local share=$SERVE_NAME user=
    if [ $# -gt 0 ] && [ "${1#-}" = "$1" ]; then share=$1; shift; fi
    if [ "${1:-}" = -U ]; then user=${2:?-U needs a user name}; fi
    header "peer $host share $share"

    local address
    address=$(getent ahostsv4 "$host" 2>/dev/null | awk 'NR == 1 {print $1}')
    if [ -n "$address" ]; then
        pass "$host resolves to $address"
    else
        fail "$host does not resolve (try the IP address, or $host.local)"
        address=$host
    fi
    case $host in
        *.*|[0-9]*) ;;
        *) getent hosts "$host.local" >/dev/null && pass "$host.local resolves over mDNS" \
               || warn "$host.local does not resolve over mDNS" ;;
    esac
    have nmblookup && info "NetBIOS: $(nmblookup -A "$address" 2>/dev/null | grep -m1 '<00>' | awk '{print $1}' || true)"

    if ping -c 2 -W 2 "$address" >/dev/null 2>&1; then
        pass "$address answers ping"
    else
        warn "$address does not answer ping (Windows blocks ping by default)"
    fi
    if timeout 5 bash -c "exec 3<>/dev/tcp/$address/445" 2>/dev/null; then
        pass "TCP 445 on $address accepts connections"
    else
        fail "TCP 445 on $address refused or timed out (server not running, or a firewall)"
    fi

    local listing
    if listing=$(smbclient -L "//$address" -N -g 2>&1); then
        pass "anonymous share list from $address"
        printf '%s\n' "$listing" | grep '^Disk|' | detail
    else
        info "anonymous share list refused (normal for Windows): $(printf '%s' "$listing" | tail -1)"
    fi

    round_trip "guest" "//$address/$share" -N
    if [ -n "$user" ]; then
        local password=${SPACED_SMB_PASSWORD:-}
        if [ -z "$password" ]; then
            read -r -s -p "Password for $user on $host: " password
            echo
        fi
        round_trip "user $user" "//$address/$share" -U "$user%$password"
        smbclient "//$address/$share" -U "$user%$password" -c 'quit' -m SMB3 >/dev/null 2>&1 \
            && pass "SMB3 negotiated with $address" || warn "SMB3 not negotiated with $address"
    fi

    # The path Caja and Gigolo use (GVfs), not smbclient.
    local uri="smb://$address/$share" mounted=0
    if gio mount -a "$uri" </dev/null >/dev/null 2>&1 || gio info "$uri" >/dev/null 2>&1; then
        mounted=1
        if gio list "$uri" >/dev/null 2>&1; then
            pass "GVfs (Caja/Gigolo) opens $uri as guest"
            local work
            work=$(mktemp -d)
            payload "$work/up"
            if gio copy "$work/up" "$uri/spaced-gvfs-$$.bin" 2>/dev/null \
                && gio copy "$uri/spaced-gvfs-$$.bin" "$work/down" 2>/dev/null \
                && cmp -s "$work/up" "$work/down"; then
                pass "GVfs copy to and from $uri round-trips"
            else
                fail "GVfs copy to or from $uri failed"
            fi
            gio remove "$uri/spaced-gvfs-$$.bin" >/dev/null 2>&1
            rm -rf "$work"
        else
            fail "GVfs mounted $uri but cannot list it"
        fi
    else
        info "GVfs anonymous mount of $uri refused; open it in Caja with a user name to test authenticated GVfs"
    fi
    [ "$mounted" -eq 0 ] || gio mount -u "$uri" >/dev/null 2>&1

    info "waiting 30 seconds for network browsing (mDNS and WS-Discovery)"
    gio list network:/// >/dev/null 2>&1
    sleep 30
    local browse
    browse=$(gio list -a standard::display-name network:/// 2>/dev/null)
    printf '%s\n' "$browse" | detail
    # Match by name even when the peer was given as an address.
    local name names=${host%%.*}
    case $host in
        [0-9]*) names=no-name-for-this-address
                for name in $(getent hosts "$address" | cut -d' ' -f2-) \
                    $(nmblookup -A "$address" 2>/dev/null | awk '/<00>/ && !/GROUP/ {print $1; exit}'); do
                    names="$names|${name%%.*}"
                done ;;
    esac
    if printf '%s\n' "$browse" | grep -Eqi -- "$names"; then
        pass "$host appears in Network (Caja's Browse Network)"
    else
        warn "$host does not appear in Network (pass the peer's NAME.local to match by name); direct addresses still work"
    fi
}

touch "$LOG" || exit 1
case ${1:-} in
    local) check_local ;;
    serve) shift; serve "$@" ;;
    peer) shift; check_peer "$@" ;;
    *) sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
say "--- $fails failed, $warns warnings; log: $LOG"
exit "$fails"
