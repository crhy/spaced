#!/bin/sh
# Spaced session guard: a package upgrade must never stop the elogind that owns
# the running desktop session. invoke-rc.d asks this script (installed as
# /usr/sbin/policy-rc.d by spaced-mate-default-settings) before every action:
# exit status 101 means "forbidden", so invoke-rc.d runs nothing and reports
# success to the maintainer script. The upgraded elogind binary is then simply
# used at the next restart. Called as:
#   policy-rc.d [--quiet] [--list] <service> <actions> [<runlevel>]
# Only elogind stop/restart/reload is refused while a desktop is running;
# elogind start and every other service are always allowed. Never prints.

RUN_USER_DIR=${SPACED_POLICY_RUN_USER:-/run/user}

# Skip invoke-rc.d's own leading options (--quiet, --list, ...).
while [ $# -gt 0 ]; do
    case $1 in
        -*) shift ;;
        *) break ;;
    esac
done
[ "${1:-}" = elogind ] || exit 0
shift

# The actions may arrive as separate arguments or as one space-separated
# argument, so match the joined list.
case " $* " in
    *" stop "*|*" restart "*|*" try-restart "*|*" force-reload "*|*" reload "*) ;;
    *) exit 0 ;;
esac

pgrep -x Xorg >/dev/null 2>&1 && exit 101
for session in "$RUN_USER_DIR"/*/; do
    [ -d "$session" ] && exit 101
done
exit 0
