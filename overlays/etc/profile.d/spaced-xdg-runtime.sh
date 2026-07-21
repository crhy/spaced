# Spaced Linux: ensure a writable XDG_RUNTIME_DIR.
# sysvinit provides no logind, so this is never set automatically; dconf needs
# it or `gsettings set` silently fails (the desktop stays on built-in defaults).
if [ -z "${XDG_RUNTIME_DIR:-}" ]; then
    export XDG_RUNTIME_DIR="/tmp/runtime-$(id -u)"
fi
if [ ! -d "$XDG_RUNTIME_DIR" ]; then
    mkdir -p "$XDG_RUNTIME_DIR" 2>/dev/null
    chmod 700 "$XDG_RUNTIME_DIR" 2>/dev/null
fi
