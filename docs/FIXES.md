# Spaced Linux resolution record

This file records the current resolution of recurring issues found while developing the 7.26 and 8.26 images. It is a historical resolution log, not the primary architecture guide.

Current theme architecture is documented in [MATE-theming.md](MATE-theming.md). Current palette and color ownership are documented in [THEME-COLORS.md](THEME-COLORS.md).

Verified against commit `f462bdb4b4d3916caf1617159056f2743b016acf`.

| Area | Current resolution | Main implementation |
|---|---|---|
| Calamares launcher | The desktop launcher is executable, says **Install Spaced Linux**, and uses Spaced branding. Debian module defaults remain available, while unwanted launcher/branding conflicts are removed during image construction. | `overlays/etc/skel/Desktop/install-spaced-linux.desktop`, Calamares overlay, image hook |
| Installer slideshow | The slideshow uses valid Calamares `Presentation`/`Slide` QML and the installer enforces a 5 GB storage minimum. | `overlays/etc/calamares/` |
| Theme warning or question-mark state | The image has **ten selectable MATE metathemes** plus the internal `Spaced-Dark` engine. Every selectable theme has GTK2, GTK3, top-level metatheme metadata, Metacity metadata, a valid icon overlay, wallpaper metadata, and a static preview. | `overlays/usr/share/themes/`, `themes.json`, `scripts/check.sh` |
| Invisible check boxes and radio buttons | Controls are CSS-rendered. The shared asset file resets fallback `background-image` and icon state, then supplies explicit shape, state, and symbolic glyph rules. Per-theme tail rules provide checked colors. | `Spaced-Dark/gtk-3.0/gtk-widgets-assets.css`, per-theme `gtk.css` |
| GTK fallback blue covering control colors | `background-image: none`, `-gtk-icon-source: none`, and `-gtk-icon-shadow: none` are applied to the shared indicator nodes before checked-state glyphs are added. | `gtk-widgets-assets.css` |
| CCSM and other special surfaces | Shared and application-specific GTK rules give special windows the active theme background and foreground instead of relying on incomplete fallback styling. | `Spaced-Dark/gtk-3.0/`, especially `spaced-overrides.css` and app CSS |
| Theme clutter | `scripts/check.sh` allows exactly the ten registered/selectable theme directories and excludes the internal `Spaced-Dark` directory from the top-level selectable set. | `scripts/check.sh` |
| Indistinct folder previews | Every selectable metatheme names a separate lightweight `Spaced-Icons-*` overlay. Overlays own scalable folder/home artwork and inherit the remaining set from shared menu overlays, Papirus Dark, and hicolor. | `overlays/usr/share/icons/Spaced-Icons-*` |
| Root-owned Papirus mutation | Removed. Theme switching never rewrites Papirus folder symlinks. Folder color is fixed by the selected icon overlay. | metatheme `IconTheme=...`; no runtime folder-rewrite function |
| Wallpaper flicker or solid background | MATE's settings daemon is the sole wallpaper painter. Polling, Caja restarts, root-pixmap helpers, background toggles, conversion steps, and Compiz background restarts are not part of normal switching. | GSettings override, `spaced-switch-theme`, `spaced-theme-monitor` |
| Lost user wallpaper after login | The monitor restores GTK/icon/window choices, applies registered theme extras, then restores the saved wallpaper. | `overlays/usr/local/bin/spaced-theme-monitor` |
| Theme watcher overhead | The retired two-second poller was replaced by one system-wide `gsettings monitor` integration process with a runtime lock. | `spaced-theme-monitor`, `/etc/xdg/autostart/spaced-theme-monitor.desktop` |
| Theme-name case ambiguity | The current registry lookup is exact and case-sensitive. Theme names in MATE, `themes.json`, and directory names must match exactly. | `spaced-theme-monitor` |
| External themes retaining Spaced extras | This remains a known behavior: an unregistered GTK theme does not trigger `spaced-switch-theme`, so a previous explicit panel color, panel edge, terminal color, or dock state may remain. | current monitor registry lookup |
| Compiz silently falling back | MATE requires `spaced-window-manager`. It verifies X/GLX and starts `compiz ccp --replace`; if Compiz is unavailable, the session fails instead of silently substituting another window manager. | `overlays/usr/local/bin/spaced-window-manager` |
| Compiz profile location | The active seeded INI profile is `~/.config/compiz/compizconfig/Default.ini`, copied from `/etc/skel`. It is not stored under `.config/compiz-1`. | `overlays/etc/skel/.config/compiz/compizconfig/` |
| Window decorator ownership | `spaced-window-manager` starts Compiz. Compiz's decoration plugin separately runs `gtk-window-decorator --replace`. | Compiz `Default.ini` |
| Notification-area crash during theme switching | The switch helper moves and resizes the existing panel. It never runs `mate-panel --replace`, preserving the notification-area X selection. | `spaced-switch-theme` |
| Panel color mismatch | Panel widget CSS and optional MATE toplevel background colors are documented and tested as separate channels. | theme CSS, `themes.json` `panel_color` |
| Static preview mismatch | `preview.png` is treated as a separate artifact from live GTK CSS. Visual changes must be tested live and reflected in the static preview independently. | each theme's `preview.png` |
| Flatpak theme files missing | Registered theme switches copy real theme directories to `~/.local/share/themes`, grant read access, and set a user Flatpak `GTK_THEME` override. | `spaced-switch-theme` |
| Flatpak stale after package update | A later registered theme switch refreshes the user-local copies. The user-local copy can otherwise shadow `/usr/share/themes`. | GTK search order and switch helper export |
| Qt/GTK mismatch | Qt Widgets are directed toward GTK platform integration. Qt Quick Controls remain a separate fixed Universal Dark configuration and are not claimed to follow light Spaced themes. | profile script and `qtquickcontrols2.conf` |
| GTK4/libadwaita mismatch | GTK4/libadwaita applications are explicitly outside the guaranteed GTK3 theme coverage. | documentation boundary; no GTK4 theme engine is shipped |
| Excess RAM and package bloat | Duplicate wallpaper/theme daemons and a stranded decorator process were removed. Tracker autostart remains disabled. Cairo Dock is reduced to its core package, and unused helpers are omitted. | package list, autostart overlays, session scripts |
| KVM input/display drift | Interactive launchers use one standard VGA device, GTK display, USB keyboard/tablet, KVM acceleration, and SSH forwarding. Unattended smoke testing uses VNC/framebuffer capture and verifies the MATE session, panel, Caja, and Compiz. | VM scripts and Makefile |
| Dual-GPU test-VM black screen | Test paths use one `-vga std` device and reject layered virtio VGA devices. | VM scripts and `scripts/check.sh` |
| Rebuild time | The live-build package/bootstrap cache lives under `build/cache/live-build` and survives normal clean builds; `make cache-clean` removes it explicitly. | Makefile |
| Mirror-sync build failures | Build-time repositories use the configured Devuan merged mirror consistently across phases. | live-build configuration |
| Flathub build failure | The image build does not depend on live Flathub network access inside the chroot. Login-time and wrapper helpers register usable remotes when networking is available. | image hook, Flatpak helper scripts |
| systemd-free Devuan policy | Full systemd and `systemd-sysv` remain forbidden. The build permits only the standalone sysusers/tmpfiles tools required by Debian packages; they do not install systemd as the init system. | `dependency.json`, package manifest, live-build exclusions, `scripts/check.sh` |
| Installed-system theme updates | The `spaced-mate-default-settings` package stages every `Spaced-*` theme plus icons, helpers, schemas, layouts, and related desktop files. Local same-version builds must be installed explicitly with `dpkg -i`. | `scripts/iso/build-local-packages.sh`, package control/postinst |

## Validation

Before building or committing:

```bash
make check
```

For a live image:

```bash
make iso-build
make iso-test
```

For an installed-system update test:

```bash
scripts/iso/build-local-packages.sh
version=$(cat VERSION)
sudo dpkg -i "build/local-packages/spaced-mate-default-settings_${version}_all.deb"
```

A resolution in this file should be updated when the implementation changes. Do not preserve obsolete paths or helper names merely as historical context; use Git history for superseded implementations.
