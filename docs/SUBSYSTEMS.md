# Spaced Linux subsystem maintenance map

Updated 23 October 2026 after 10.26.6. This map connects implementation,
delivery and validation; historical release reviews remain unchanged.
Start with the [current issue audit](10.26.6-POST-RELEASE-AUDIT.md),
[resolution record](FIXES.md) and [Compiz guide](COMPIZ.md).

| Subsystem | Source / delivery | Findings and validation boundary |
|---|---|---|
| Base, init and image | `config/`, `scripts/iso/`, `live-build/`; Devuan Ceres, sysvinit | Keep systemd and systemd-sysv excluded. Standalone sysusers/tmpfiles utilities do not change init. Verify the built image, not just package-list intent. |
| Boot and installation | GRUB templates, `overlays/etc/calamares/`, restart helper; ISO and settings package | Live boot mounts SquashFS with a writable overlay. After eject, on-demand pages disappear; pre-importing Python/GTK does not make Xorg or the process resident. The 10.26.6 restart guard locks its mappings and prepares input/reboot handles before the prompt. Test actual ejection. See [booting](BOOTING.md). |
| User creation | Calamares live-user removal and users configuration | Remove live UID 1000 before creating the installed user and pre-create system groups. Verify installed UID, absence of live account, autologin and sudo behavior. |
| Window management | Compiz queue, launcher, decorator, INI migrations; matching native packages | Pixmap lifetime and libmarco geometry fixes ship. Internal exec-to-Marco remains possible; PID continuity is insufficient. See [Compiz](COMPIZ.md). |
| Themes, panel and wallpaper | `spaced-switch-theme`, monitor, `themes.json`, schemas, layouts; settings/themes/wallpapers packages | MATE owns wallpaper; move the existing panel instead of restarting it. Close inherited flock descriptors in background children. Theme engine, preview images, Qt and Flatpak need separate checks. See [MATE theming](MATE-theming.md), [colors](THEME-COLORS.md), [panel](matepanel.md). |
| Application toolkit integration | Xsession `40spaced-application-theming`, profile configuration, theme export | GUI applications need the Xsession environment, not just shell profile variables. Qt Widgets and Qt Quick have different paths. GTK4/libadwaita is outside guaranteed GTK3 styling. Existing Flatpak theme copies can shadow system updates until refreshed. |
| Audio | `spaced-audio-restore`; settings package | Persist named card profiles as well as named sink volume/mute. Restore profiles before selecting output; validate saved profiles against current capabilities and retain disconnected-device state. Old volume-only tests do not cover USB DAC profile persistence. |
| Display and GPU recovery | Graphics manager, AMD/NVIDIA helpers, Xrandr repair; native settings | Collect PCI IDs, renderer, connector/EDID, kernel and DKMS logs. Hardware branch guards and a successful VM do not validate a physical GPU. Recovery code 52 means incomplete recovery. See [GPU recovery](NVIDIA-RECOVERY.md). |
| Caja file operations | `patches/caja/` and rebuilt Caja packages | The 10.26.6 cross-filesystem conflict-rename fix preserves the chosen destination; upstream PR 1888 was merged and backported. Copy cancellation hanging (#355) is a different unresolved behavior. |
| Sharing and discovery | Samba configuration, sysvinit WSD service, NetworkManager dispatcher and sharing helpers | Reconnect needs discovery/service refresh. Traversal permission on `/home` is not directory listing permission; Samba credentials are distinct from share browsing. Verify authenticated access and permissions. Checksums establish integrity, not throughput; the concurrent-traffic SMB tests do not resolve #363. |
| OS updates | `overlays/usr/lib/spaced-linux/spaced-update.py`, `spaced-update-helper`, `spaced-update-refresh`; main repository APT packages | This is the shipped source, not `crhy/spacedupdate`. Configure pending packages, check dependencies, retry once, propagate persistent failure. Flush triggers and reread installed version. A newer GitHub tag without matching APT packages causes repeated offers. |
| Welcome | Separate `crhy/spacedwelcome` repository; released Debian dependency | Main-repository changes alone do not ship a Welcome fix. Suggested-app emphasis (#11) remains pending. |
| Bazaar and end-user apps | Separate `crhy/spacedbazaar`; signed Flatpak OSTree catalog and AppStream | GitHub asset publication is not Flatpak catalog publication. Refresh metadata at both scopes; verify origin, installed ref and actual available commit. See [application delivery](APPLICATION-DELIVERY.md). |
| Voxa and other suggested apps | Independently released application artifacts and Welcome/catalog integration | Desktop actions, speech errors and onboarding are tracked separately. Do not attribute a full-machine crash to Voxa or Compiz without kernel and memory evidence. |
| Packaging and publication | `scripts/iso/build-local-packages.sh`, `scripts/build-apt-repo.sh`, `make apt-repo-publish` | Never republish different bytes under a released Debian version. Reuse published pinned artifacts when rebuilding a nonreproducible dependency. Publish signed APT before/with the OS release and verify downloaded assets. |

## What the 10.26.6 evidence establishes

The [release review](10.26.6-RELEASE-REVIEW.md) records 244 unit tests and two
GTK tests, BIOS/UEFI boots on KVM and VirtualBox, and all 13 themes on each
of those four final-ISO configurations. The installation candidate exercised
Calamares, installed-user identity, package health and real ISO ejection.
The resident guard used 23,244 KiB and reached installed login after restart
in 23 seconds in that test environment; these are observations, not hardware
minimums or a general boot-time guarantee.

The signed APT publication and public ISO bytes were verified. SMB testing
checked bidirectional data integrity and file operations with a Spaced peer;
it was not a controlled throughput benchmark or Windows 11 certification.
Affected physical AMD/NVIDIA hardware, Wi-Fi roaming and suspend/resume
remain outside that release's demonstrated coverage.

## Updating this documentation

For a new finding, record the failing behavior, owning source, delivery
channel, version, reproducer and observed result. Distinguish a source-level
explanation from an end-to-end hardware result. Update living architecture
guides and this map when ownership changes. Add a new dated audit or revision
entry for later evidence; do not rewrite published changelog entries or old
issue-status snapshots. Close issues only after the implementation is merged
and any independently released component has shipped it.
