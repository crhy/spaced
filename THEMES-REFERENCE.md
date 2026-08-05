# Spaced Linux 8.26 — MATE Themes & Preferences Reference

## How theming works (the pipeline)

User picks a theme (Appearance capplet, our chooser, or `gsettings`) → writes
`org.mate.interface gtk-theme = "Spaced-<Name>"` → **spaced-theme-watch** (autostart)
polls that key every 2s → resolves it to a theme id via `themes.json` → runs
**spaced-switch-theme <id>** which applies: GTK/icon theme, folder color, wallpaper,
panel layout, cairo-dock.

Two watchers autostart (both in `overlays/home/user/.config/autostart/`):
- `spaced-theme-watch` — reacts to gtk-theme changes; does the real work.
- `spaced-wallpaper-watch` — only keeps the bg plugin enabled (harmless fallback).

## Key files (all under `overlays/`)
- `usr/local/bin/spaced-theme-watch`   — gtk-theme poller + `ensure_wallpaper`
- `usr/local/bin/spaced-switch-theme`  — applies a theme id
- `usr/local/bin/spaced-init-session`  — runs at login; clears stale wallpaper state, applies default theme
- `usr/share/spaced-themes/themes.json` — the theme registry (see below)
- `usr/share/glib-2.0/schemas/90_spaced-linux.gschema.override` — default gsettings
- `usr/share/themes/Spaced-*/preview.png` — Appearance Preferences thumbnails
- `usr/share/fastfetch/logos/spaced-linux.txt` — fastfetch ascii logo

## themes.json shape
Each entry: `id, name, wallpaper, panel_layout, gtk_theme, icon_theme,
folder_color, cairo_dock, cairo_dock_position, panel_position, panel_size`.
`gtk_theme` is what MATE stores in `org.mate.interface gtk-theme`.
`folder_color` is a Papirus color name (grey/green/teal/blue/bluegrey).

Current mapping (folder_color → wallpaper):
- default → grey / SpacedBack.jpg      (gtk_theme: Spaced-Dark)
- macos   → blue / macos.jpg           (cairo_dock, top panel)
- win311  → bluegrey / win311.jpg
- winxp   → blue / winxp.jpg
- android → teal / android.jpg          (cairo_dock, top panel)
- mint    → green / linuxmint.jpg       (cairo_dock)
- win11-light → blue / win11light.jpg
- win11-dark  → blue / win11dark.jpg
- geoworks → bluegrey / geoworks.jpg

## Panel is identical for every theme

All nine `panel_layout`s share the exact same applet composition
(`BriskMenu`, `WindowList`, `NotificationArea`, `GvcApplet`, `Clock`,
`ShowDesktop`, all `locked=true`); the layout files differ only in the
toplevel's orientation. `panel_position` in `themes.json` moves the panel to
the top edge for Android and Mac OS X; `cairo_dock=true` for those two also
launches the dock at the bottom. See `docs/matepanel.md` for the full panel
specification.

## Folder colors (Papirus)
`spaced-switch-theme set_folder_color` repoints every `places/folder.svg`
symlink in Papirus/Papirus-Dark/Papirus-Light to `folder-<color>.svg`, across all
sizes incl `@2x`, as root (via `sudo`). Cover all sizes or the file manager / desktop
will show the wrong color.

## Wallpaper (CRITICAL — Compiz gotcha)
- The WM is **Compiz** (`compiz ccp`). Compiz does **NOT** display the X root pixmap
  that `feh` paints. `feh` therefore does nothing visible under Compiz.
- The reliable painter is **mate-settings-daemon's background plugin**, driven by
  `gsettings set org.mate.background picture-filename <path>`.
- The plugin MUST be enabled: `org.mate.SettingsDaemon.plugins.background active true`
  (set in the gschema override). It was previously `active=false` — that is what made
  the desktop gray.
- `spaced-switch-theme` and `ensure_wallpaper` both paint via that gsettings key now.
- Wallpaper "already painted" state lives in `$HOME/.cache/spaced/wallpaper-current`
  (NOT `/tmp` — `/tmp` is persistent and a stale/root-owned value made the watcher skip
  painting). `init-session` deletes this file at boot.

## Theme-name case trap
MATE lowercases the theme name it stores: `Spaced-WinXP` becomes `Spaced-Winxp`,
`Spaced-MacOS` → `Spaced-Macos`, `Spaced-Win11-Light` → `Spaced-Win11-light`.
`gtk_to_id` in `spaced-theme-watch` matches **case-insensitively** against
`themes.json`'s `gtk_theme`. If you add a theme with uppercase in its gtk_theme, this
is why a switch may be silently skipped.

## Watcher robustness notes
- Single-instance guard uses a `flock` on `$LOCK.watch` (NOT `pgrep -f`, which matches
  the parent shell and self-kills the watcher).
- `apply_theme` uses a **blocking** `flock 9` so rapid successive theme changes queue
  and each completes (a non-blocking flock silently dropped switches → desktop stuck on
  an old theme's folder/wallpaper).
- `cairo-dock` is launched with `9>&-` so the flock fd does not leak to it.

## cairo-dock
- Needs `python3-dbus` (package added to `config/packages.yaml` dock group); without it
  the launcher API daemon crashes with `ModuleNotFoundError: No module named 'dbus'` and
  the dock never appears.

## Changing things safely
- Edit `themes.json`, then the next gtk-theme write applies it (no rebuild needed for
  live testing — but the ISO is the source of truth; reboot reverts the running VM to
  the ISO's files).
- After editing any `overlays/` file, **rebuild the ISO** (`make iso-build`) for it to
  persist; the running VM reverts to the ISO on reboot.
- Rebuild gotcha: clear stale chroot binds first or `make prepare` fails:
  `sudo umount -l build/live-build/chroot/{sys,proc,dev/pts,dev}`.

## Verification cheat-sheet (VM)
- Boot ISO; SSH `user`/`1`, port 2222 (`-nic user,hostfwd=tcp::2222-:22`).
- Get session DBUS: `DBUS=$(tr '\0' '\n' < /proc/$(pgrep mate-panel)/environ | grep DBUS_SESSION_)`.
- Drive a theme: `DBUS_SESSION_BUS_ADDRESS="$DBUS" gsettings set org.mate.interface gtk-theme Spaced-WinXP`.
- Check: `readlink /usr/share/icons/Papirus-Dark/64x64/places/folder.svg`,
  `cat $HOME/.cache/spaced/wallpaper-current`,
  `xprop -root _XROOTPMAP_ID` (must be a non-empty pixmap id = wallpaper painted).
- `DISPLAY=:0` MUST be exported in any subshell that runs `xprop`/`feh`, or checks read empty.
