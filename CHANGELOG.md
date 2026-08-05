# Changelog

## 8.26 - Unreleased
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
- Made Compiz the default MATE window manager with automatic Marco fallback.
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
