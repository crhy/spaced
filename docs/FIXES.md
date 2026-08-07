# OpenCode history cleanup

This is the current resolution record for the repeated issues reported while
testing the 7.26 live image. Superseded experiments are intentionally omitted.

| Area | Resolution |
|---|---|
| Calamares launcher | `/etc/skel/Desktop/install-spaced-linux.desktop` is executable, says **Install Spaced Linux**, and uses Spaced branding. Debian's module defaults remain installed, while its launcher and branding are removed during the image build. |
| Installer slideshow | Uses valid Calamares `Presentation`/`Slide` QML and a 5 GB storage requirement. |
| Theme warning / question mark | All eleven themes contain GTK 2, GTK 3, component metadata, top-level metatheme metadata, wallpaper metadata, and a valid icon theme. |
| Invisible controls and CCSM | Check/radio controls are CSS-rendered rather than dependent on missing bitmaps. CCSM's custom window class explicitly receives the active theme's background and foreground palette. |
| Theme clutter | The image hook retains only the eleven supported Spaced themes; the incomplete `Spaced-Linux` fallback was removed. |
| Indistinct folder previews | Every metatheme names a separate lightweight icon overlay. The overlays inherit Papirus Dark and own correctly scalable folder/home SVGs in the theme's color. |
| Wallpaper flicker / solid background | MATE is the sole wallpaper painter. Wallpaper polling, Caja restarts, background toggles, image conversion, and Compiz `--bg-image` restarts were removed. |
| Compiz silently falling back | The profile moved to `.config/compiz-1`, includes the `ccp` plugin, and Compiz starts with the known-good `compiz ccp --replace` command. |
| Notification area crash | Theme changes move/resize the existing panel and never run `mate-panel --replace`. |
| Excess RAM / package bloat | Tracker autostart remains disabled. Duplicate wallpaper/theme daemons and a stranded GTK window decorator are removed. Cairo Dock is reduced to its core package, and `nvtop` plus unused image/build helpers are omitted. Broad automatic firmware injection is replaced by an explicit common-PC set, avoiding uncommon server, Qualcomm, and legacy NVIDIA payloads. The last live measurement before this cleanup was about 912 MiB used. |
| KVM input/display drift | All supported launchers use GTK, virtio GPU with 1440×900 EDID, USB keyboard/tablet, KVM acceleration, and SSH forwarding on port 2222. QXL/SPICE and legacy 6.26 launchers were removed. |
| Rebuild time | `live-build` package/bootstrap cache now lives at `build/cache/live-build` and survives normal clean builds. `make cache-clean` removes it explicitly. |
| Mirror-sync build failures | Build-time repositories use Devuan's package master rather than the rotating CDN, preventing different build phases from receiving mismatched Ceres snapshots. |
| Flathub build failure | The image no longer contacts Flathub from inside the build chroot. A small idempotent MATE autostart registers the per-user remote when networking is available. |
| systemd-free Devuan | **NO systemd packages may be included in this distro.** Spaced Linux is a Devuan distribution and uses sysvinit exclusively. `systemd`, `systemd-sysusers`, and all full-systemd packages are forbidden. Only `systemd-standalone-sysusers` and `systemd-standalone-tmpfiles` are permitted — these are standalone Debian tools that provide only the sysusers/tmpfiles D-Bus APIs without installing systemd itself, enabling packages like dhcpcd-base to configure on a sysvinit system. Debian-only packages requiring systemd (e.g., `dhcpcd-base`) must be excluded from debootstrap via `--exclude` in `live-build/auto/config`. |

Run `make check` before building. Use `make iso-build`, then `make iso-test` for
the live image and installer, or `make vm-start` after installation.
