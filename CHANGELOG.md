# Changelog

## 8.26.7 - 2026-08-22
- Made live-session time synchronization strictly optional and bounded, so an offline NTP lookup can no longer time out Calamares or leave an incomplete installed system (issues #129 and #134).
- Disabled screen blanking and locking only in the disposable live session, and granted its active local user passwordless GParted authorization while retaining normal installed-system authentication (issues #128 and #131).
- Released stale Calamares target mounts before and after each installer run so a failed attempt does not hide the Erase Disk option on retry (issue #130).
- Replaced the Calamares simple mark with the transparent fancy icon and matched the logo widget surface to the sidebar (issue #132).
- Made the installed GRUB theme self-contained under `/boot/grub/themes/spaced`, restored its fancy logo, and used theme-relative image paths that work with separate or encrypted root filesystems (issue #133).
- Put the issue-provided black/silver Brisk mark directly into every selectable icon theme during package staging so the active icon cache cannot resolve an inherited stale icon (issue #107).
- Added explicit `Signed-By` scope to the intentionally trusted Spaced APT source, removing APT 3's update notice (issue #135).
- Added Cards with Cats, Brutal Chess, and the alternate Spaced Update Flatpak to Spaced Linux Welcome and its SpacedBazaar-curated CRHY catalog alongside Voice2Text; all GitHub Flatpak bundles, including SpacedBazaar itself, now resolve their asset from each repository's latest stable release instead of pinning a versioned filename (issue #136).
- Bumped distribution, package, installer, boot, VM, website, and documentation release identifiers to 8.26.7.

## 8.26.6 - 2026-08-20
- Kept clean Ceres bootstraps systemd-free across the current `ifupdown` transition by excluding the obsolete ifupdown stack; NetworkManager remains the sole configured network manager, and the standalone sysusers/tmpfiles helpers remain explicitly included.
- Routed APT repository generation through the host toolchain so IDE/Flatpak release sessions can invoke `dpkg-deb` and `apt-ftparchive` reliably.
- Restored reliable desktop audio state across reboot and hotplug: a user-session fallback remembers the selected sink volume and mute state, corrects only the broken first-boot 0%/muted state, and leaves later intentional choices alone (issues #119, #121, and #125).
- Added an XRandR recovery helper that reasserts the active mode after login and screensaver unlock, disables driver-side underscan, clears underscan borders, and selects full-range RGB where supported (issues #116–#118).
- Made both Calamares and interactive terminals use an absolute or `/usr/local/bin`-reachable reboot command, preventing a completed live installation from falling back to the locked `user` session when `/sbin` is absent from `PATH` (issues #113 and #120).
- Re-applied Calamares's selected IANA timezone to `/etc/localtime`, refreshed `tzdata`, and retained the UTC hardware-clock policy so non-DST zones such as Hawaii cannot inherit a stale live-session offset (issue #104).
- Installed SpacedBazaar 0.1.2 as part of the suggested-app transaction, retained the working dynamic Voice2Text release URL, and kept the broken upstream Bazaar identity out of every install path (issues #108, #110, and #113).
- Seeded Audacious's documented skins-window keys once so its playlist starts attached below the player and subsequent user size and position changes remain application-owned (issue #122).
- Added `btop`, `nvtop`, `zstd`, `pulseaudio-utils`, and `tzdata` explicitly to the image package set (issue #111).
- Made Pluma the system, fresh-user, and upgraded-user default for plain text and shell scripts, and enabled Caja's persistent show-hidden-files preference (issues #124–#126).
- Strengthened GTK3 Caja rubber-band and text-selection styling so click-drag areas and copied text remain visibly highlighted across all ten themes (issue #109 and the selected-text report in #113).
- Refined the Brisk mark to silver on dark surfaces and black on light surfaces, and supplied compact matching power and privilege icons instead of oversized inherited artwork (issues #107 and #112).
- Enabled a coordinated installed-system GRUB theme using the Spaced background, higher-contrast menu typography, and a restrained timeout bar (issue #127).
- Updated every versioned website download to the exact 8.26.6 GitHub release asset path, with the release gate retaining cross-file URL and version checks (issue #115).
- Accepted the clean-built 8.26.6 ISO through its portable SHA-256 check, SquashFS/package audit, and graphical KVM plus VirtualBox BIOS/EFI boots; all three paths reached SSH and a running MATE/Compiz/Caja desktop and produced nonblank captures.

## 8.26.5 - 2026-08-15
- Bumped the release to 8.26.5 across package, ISO, bootloader, installer, website, documentation, and VM metadata.
- Released [SpacedBazaar 0.9.4-spaced1](https://github.com/crhy/spacedbazaar/releases/tag/0.9.4-spaced1), merging Bazaar 0.9.4's screenshot, navigation, focus, zoom, and performance improvements while retaining the sandbox-safe user-installation fix for issue #61. Removed an account-specific `/home/rhy` path, built and reinstalled the GNOME 50 bundle, launched it, and completed a real Flathub install from inside the sandbox.
- Fixed invisible or incomplete Dolphin check boxes by keeping the GTK-provided Qt palette while using Qt's complete Fusion widget controls (issue #78).
- Added GParted to the default desktop applications and release validation gate (issue #100).
- Replaced the thin Brisk menu “S” with a clearer round Spaced mark in light, dark, symbolic, and hicolor variants (issue #55).
- Made Caja's drag-selection rectangle visibly translucent instead of an opaque dark box, and locked the visual rule into the source gate (issue #101).
- Synced Spaced Update 8.26.4.0.2 into the native image: sandboxed Flatpak enumeration no longer returns an empty list after a successful host probe, update refs are scoped and normalized, and one broken remote cannot hide healthy updates.
- Released [Spaced Update 8.26.4.0.2](https://github.com/crhy/spacedupdate/releases/tag/8.26.4.0.2) on the supported GNOME 50 runtime, using its maintained Python/PyGObject stack; the installed Flatpak shrank from about 303 MB to 3.5 MB and gained six deterministic regression tests.
- Accepted the clean-built 8.26.5 ISO through its portable SHA-256 check, SquashFS/package inspection, and graphical KVM plus VirtualBox BIOS/EFI live boots; every VM reached SSH and a running MATE/Compiz/Caja desktop and produced a nonblank desktop capture.

## 8.26.4 - 2026-08-10
- Bumped the release to 8.26.4 across package, ISO, bootloader, installer, website, documentation, and VM metadata.
- Restored the MATE Power Management Control Center panel by adding `mate-power-manager` back to the default package set (issue #98).
- Fixed the update-repository publishing flow: `make apt-repo` and `make apt-repo-publish` now rebuild the GitHub Pages repository with only the current release's packages and push it, so Spaced Update on installed systems receives the new theme, desktop-integration, and release-marker packages instead of remaining stuck on the previous release's index.
- Made every derived theme's GTK3 CSS import its widgets through relocatable sibling-relative paths instead of absolute `/usr/share/themes` paths, so the themes keep working from any prefix (system package, unpacked archives, and sandboxes); `make check` rejects absolute imports.
- Exported the Spaced themes into sandboxed GTK apps: theme switches now mirror the system themes into `~/.local/share/themes`, grant Flatpaks read access to the theme export, and set the user-level `GTK_THEME` override, so Flatpak applications (Bazaar, VLC, and the rest) finally follow the desktop theme instead of falling back (issues #10, #45, #61).
- Published Spaced Update as a self-contained Flatpak (`org.spacedlinux.SpacedUpdate`): the manifest, build, and GitHub Pages publish flow live in the `crhy/spacedupdate` repository and bundle Python 3.13, PyGObject, and the Spaced themes; privileged APT and Flatpak work runs through the host via `flatpak-spawn`.
- Removed the visible nested-container boxes from every theme by keeping GtkBox, GtkGrid, GtkPaned, and other pure layout containers transparent instead of painting them, and flattened toolbars, breadcrumbs, and raised toolbar buttons so file managers and dialogs no longer show square tool shelves.
- Modernized the default buttons with clean 1px outlines, soft radius, calm hover/active states, and a quiet accent border on suggested actions, together with refreshed first-run application rows in the Welcome window (issue #87).
- Fixed the false “Compiz is not the active window manager” NVIDIA warning: the post-boot check now trusts the running Compiz process when `wmctrl` is missing or still catching up, waits longer for the session to settle, and the system ships `wmctrl` explicitly.
- Made standard-DPI displays explicitly set the 100% window-scaling factor instead of leaving an unset or stale factor behind, while high-density displays keep their automatic 2x scaling (issue #64).
- Made the large Voice2Text bundle download resume interrupted transfers with `curl --continue-at` and retry download plus install independently across three attempts, discarding a corrupt bundle before re-downloading.
- Cleaned Calamares branding: the transparent `spaced-logo.png` mark replaces the tiled icon in every installer image slot, the sidebar and widget surfaces use neutral grays instead of blue-tinted shades, and the Qt Quick slideshow scrollbar uses a light accent instead of the default blue (issue #86).
- Enlarged the real titlebar-button hitboxes in every Metacity theme with explicit 24 px (22 px utility) button geometry and taller titlebars, keeping glyphs centered (issue #65).
- Added `wmctrl`, the Qt Quick Controls grayscale accent file, and the transparent installer logo to the validation gate.
- Made release builds discard bootstrap caches whose core filesystem paths are not root-owned, preventing security-sensitive package installers from inheriting an unsafe build UID, and added the missing `qemu-utils` host dependency.
- Made release checksum files portable by recording the ISO basename instead of a repository-relative build path.
- Accepted the candidate through KVM and VirtualBox BIOS/EFI live boots plus a complete VirtualBox install, ISO-detached reboot, LightDM login, and installed-system audit.

## 8.26.3 - 2026-08-10
- Bumped the release to 8.26.3 across package, ISO, bootloader, installer, website, documentation, and VM metadata.
- Added unattended ISO smoke tests for KVM and VirtualBox BIOS/EFI boot paths, requiring both guest SSH and a running MATE session and retaining desktop screenshots.
- Made the live LightDM session reuse Plymouth's active VT so headless KVM does not leave Xorg blocked forever waiting for a tty1-to-tty7 switch; the setting is removed with the live-only configuration during installation.
- Made Calamares use Qt software rendering so the installer slideshow remains responsive with VirtualBox VMSVGA, and set its deterministic offline starting location to Los Angeles.
- Fixed the reproducible initramfs “Unable to find a medium containing a live file system” failure by removing `live-media-timeout=60`; with the shipped live-boot logic that value delayed scanning until the search loop had already ended.
- Removed the live account from the installed LightDM base configuration, exposed the user list for remembered-user login, and added AccountsService explicitly.
- Fixed drive, optical-media, ISO, and volume icon fallback across every theme by resolving scalable Papirus assets before low-resolution hicolor fallbacks.
- Made suggested Flatpak installs retry independently and continue past a failed application, and added the keyring and GTK portal-support packages explicitly.
- Added Caja's administrator extension, Gigolo Windows-share browsing, and Timeshift backup support.
- Made Spaced Update reread `/etc/os-release` after APT completes and distinguish a successful package update from a repository that has not yet delivered the newest `spaced-meta` release marker.

## 8.26.2 - 2026-08-07
- Fixed the real-hardware boot regression that broke 8.26: the live kernel command line carried `console=ttyS0`, leaving the display blank with a blinking cursor, and an unconditional `S0` serial getty in `/etc/inittab` caused sysvinit's `INIT: Id "S0" respawning too fast` loop on machines without a usable serial port. The serial console was removed from the live image; headless access remains available through SSH, and the QEMU headless script already used `-serial none`.
- Fixed the remaining real-hardware boot regressions in the live GRUB menu: the default entry still passed the QEMU-only `video=Virtual-1:1280x1024` display, which leaves real machines on a blank screen with a blinking cursor, and the default boot append line forced `nouveau.modeset=1`, which can hang NVIDIA hardware before the desktop loads. The live menu no longer passes any `video=` argument and the default boot no longer forces GPU modesetting; the safe graphics entry uses a clean `nomodeset` line, and a new verbose boot entry (`noplymouth console=tty0 noquiet loglevel=7`) captures the full boot log for diagnosis.
- Documented the complete live boot chain, stock-Devuan comparison, all historical boot failures, and troubleshooting in `docs/BOOTING.md`, and hardened `make check` to reject `video=`, `Virtual-1`, `console=ttyS0`, and forced early `nouveau.modeset=1` so these regressions cannot ship again.
- Fixed the test-VM black screen: the QEMU harness exposed two GPUs (an explicit virtio-gpu on top of the default VGA), which stalled the guest's X and left an autologin on a blinking cursor. `make iso-test` and `iso-test-safe` now use a single `-vga std`, and `make check` rejects a second virtio GPU.
- Bumped the release to 8.26.2 across package, ISO, bootloader, installer, website, documentation, and VM metadata.

## 8.26 - 2026-08-05
- Began the 8.26 release transition across package, ISO, bootloader, installer, website, documentation, and VM metadata; QEMU now derives its default ISO filename from `VERSION` to prevent drift.
- Changed the post-install app to resolve the newest `crhy/Voice2Text-AI` GitHub release at install time instead of shipping a stale versioned bundle URL.
- Added a non-destructive MATE panel migration that restores any missing canonical applets on upgraded profiles without resetting user-added panel content (issue #83).
- Enlarged GTK dialog controls and every Compiz/Metacity titlebar button target, with full-height titlebar painting across all ten selectable themes (issue #65).
- Added high-contrast modern GTK switch styling so on/off position is visible in MenuLibre and other GTK 3 interfaces.
- Added per-user web MIME defaults for fresh accounts, complementing the system Brave handlers so links cannot silently fall back to Pluma (issue #35).
- Expanded the source validation gate to enforce cross-file release consistency, current Voice2Text resolution, all shipped shell/Python syntax, panel migrations, titlebar metrics, switch visibility, and non-executable image assets (issue #46).
- Corrected the documentation to describe Ceres as Devuan's rolling unstable suite rather than assigning it a numbered Freia release.
- Rebuilt Spaced Update with a polished theme-aware interface, clear selectable update rows and staged progress, while moving raw command output into one collapsed Technical details panel (spacedupdate issue #3).
- Moved generated local packages out of the privileged live-build cache so ordinary developer rebuilds cannot be blocked by stale root-owned output, and removed duplicate package/repository scans from the validation pass.
- Routed GRUB font staging, package-list generation, and local Debian package builds through the Flatpak host bridge so IDE-driven ISO builds use the required host tools and Python modules.
- Added a checksum-verified temporary Ceres transition pin for `xkb-data 2.47-1`, resolving the repository window where `keyboard-configuration 1.248` rejects the newly published 2.48 package.
- Corrected the internal 8.26 release codename and aligned the desktop configuration reference with the actual default Spaced Linux Dark theme and JPEG wallpaper.
- Preserved GTK, icon, and wallpaper choices across reboot with an event-driven per-user fallback for first-installed-account dconf state, without polling or overriding custom backgrounds.
- Made the host and privilege runners overridable so automated or IDE builds can avoid a blocked graphical PolicyKit prompt.

## 7.26.5 - 2026-08-01
- Replaced the Voice2Text screenshot with the current 1920x1080 capture in the Calamares slideshow, on the website showcase, and in the README gallery.
- Fixed the double volume icon by disabling the mate-media tray applet autostart so only the panel's GvcApplet renders.
- Unified all 9 panel layouts: every theme now uses the identical applet set (Brisk Menu, Window List, Volume, Notification Area, Clock, Show Desktop) with locked panels, differing only by orientation. Android and Mac OS X place the panel on top with the cairo-dock at the bottom; all other themes keep the bottom panel.

## 7.26.4 - 2026-07-31
- Fixed the live-build debootstrap failure by excluding dhcpcd-base, which depends on systemd packages that Devuan does not provide.
- Guaranteed a systemd-free system: only the standalone systemd-standalone-sysusers and systemd-standalone-tmpfiles helpers are used, never systemd itself.
- Fixed the mate-session-manager dependency conflict: spaced-mate-default-settings now Provides an exact-version debian-mate-default-settings plus mint and ubuntu variants, with matching Conflicts and Replaces, so the MATE session can start.
- Fixed the panel "VolAppletFactory::VolumePagerApplet" loading error by switching all 9 panel layouts from the obsolete MATE 1.x volume applet IID to GvcAppletFactory::GvcApplet (MATE Panel 1.27).
- Fixed the Compiz default effects: Clone Output and Expo are now disabled by default, and Paint fire on the screen (firepaint) is enabled. Distracting wobbly/animation effects remain off.

## 7.26.3 - 2026-07-28
- Fixed the GRUB Unicode font warning and restored the Spaced boot background.
- Safe Graphics now keeps normal display modes available instead of forcing the old 800x600 framebuffer.
- Added 1024x768 and 1920x1080 QEMU test targets.
- Pinned live builds to a fixed Devuan mirror and added retry handling for the MATE session package download.

## 7.26.2 - 2026-07-27
- Restored out-of-box Wi-Fi support in the live and installed systems.
- Added wpasupplicant, wireless-regdb, iw, and rfkill explicitly.
- Expanded firmware coverage for Intel, Realtek, Atheros, Broadcom, and MediaTek wireless hardware.
- Verified wireless networking on physical laptop hardware.

## 7.26 - 2026-07-22
- Updated the release to Devuan Ceres with sysvinit.
- Made Compiz the MATE window manager.
- Added the complete Spaced Linux desktop, package, installer, and live-boot configuration.

## 6.26 - 2026-06-19
- Initial release of Spaced Linux 6.26
- Based on Devuan Ceres (rolling, sysvinit)
- MATE desktop with WinXP-style single bottom panel
- Spaced-Dark theme (monochrome, Blackbird-based)
- Wallpaper via MATE desktop management
- Brisk menu with Spaced icon
- Fancy Spaced Linux logo for login screen
- Calamares installer integration
- Built with live-build
