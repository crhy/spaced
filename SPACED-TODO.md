# Spaced Linux Release and Polish To-Do

This is the master engineering checklist for the Spaced Linux 7.26.4 release line. Individual work items are tracked as GitHub issues wherever practical.

Current development branch: `agent/fix-nvidia-live-boot`  
Current draft pull request: `#18` — Harden NVIDIA installation and safe graphics boot  
Latest backed-up implementation commit: `d2302ae` — Harden NVIDIA driver installation

## Completed or already implemented on the current branch

- [x] Replace the physical NVIDIA Safe Graphics entry with the standard `nomodeset` fallback.
- [x] Remove the forced `console=ttyS0` boot argument.
- [x] Remove the active ttyS0 getty that caused SysVinit respawn warnings.
- [x] Repair the Spaced NVIDIA Driver Installer GUI startup crash.
- [x] Add a hardened NVIDIA installation helper with prerequisite checks, rollback, module verification, and reboot handling.
- [x] Add post-reboot NVIDIA, OpenGL, MATE, Caja, and Compiz verification code.
- [x] Add a renderer-aware Compiz launcher so NVK/Zink can use the software workaround while proprietary NVIDIA uses hardware OpenGL.
- [x] Put the Spaced NVIDIA Driver Installer in the Brisk menu's **System Tools** section.
- [x] Push the hardened NVIDIA work to GitHub as commit `d2302ae` on the draft PR branch.

## Release blockers — NVIDIA and Compiz

- [ ] Finish end-to-end physical validation of the hardened NVIDIA installer on the RTX 4070 Ti Super.
- [ ] Confirm the installer selects the correct NVIDIA open/proprietary module flavor.
- [ ] Guarantee exact running-kernel headers and DKMS build prerequisites are available before changing the active graphics stack.
- [ ] Remove every live-only or stale rule that blacklists NVIDIA on an installed system.
- [ ] Disable Nouveau only after all required NVIDIA modules have been built and verified.
- [ ] Verify `nvidia`, `nvidia_modeset`, `nvidia_uvm`, and `nvidia_drm` are present for the running kernel.
- [ ] Verify the rebuilt initramfs actually contains the required NVIDIA modules.
- [ ] Remove stale `nomodeset`, Nouveau, NVIDIA, and Xorg configuration that would prevent automatic driver selection.
- [ ] Roll back automatically to a bootable Nouveau/Mesa configuration after any failed NVIDIA transaction.
- [ ] Add a complete Secure Boot/MOK enrollment flow, or a clear guided fallback that makes no driver changes.
- [ ] Verify the post-reboot desktop is using proprietary NVIDIA OpenGL rather than NVK/Zink or llvmpipe.
- [ ] Verify Compiz starts automatically after the NVIDIA reboot and never falls back to Marco at runtime.
- [ ] Verify the Restore Nouveau workflow from the graphical app.
- [ ] Test the installer on older supported NVIDIA generations as well as current Ada hardware.

Existing umbrella issue: **#2 — Nvidia/Radeon Drivers in Devuan**.

## Release blockers — login, session, and installed-system cleanup

- [ ] Fix the LightDM-to-user-session handoff so elogind/PAM cannot terminate LightDM during login.
- [ ] Remove duplicate `pam_systemd.so`/`pam_elogind.so` session hooks from the greeter PAM stack.
- [ ] Ship installed-system LightDM settings with `xserver-share=false`, MATE as the session, and no live autologin.
- [ ] Ensure Calamares removes every live-only LightDM/autologin file after installation.
- [ ] Remove unsupported Cairo-Dock/Metacity/Default Xsession login choices while keeping Cairo-Dock available inside the MATE desktop.
- [ ] Force MATE as the default desktop for every newly installed user.
- [ ] Ensure `/usr/local/bin/spaced-window-manager` is executable, discoverable in the session environment, and selected as MATE's window manager component.
- [ ] Remove remaining live packages, installer launchers, transient users, passwords, SSH overrides, and live configuration from the installed system.

## Release blockers — MATE panel and sound

- [ ] Ship one canonical MATE panel layout for every new user.
- [ ] Restore the Brisk menu, notification area, network indicator, clock, workspace controls, and any intended launchers after first login.
- [ ] Restore a working sound/volume icon in the notification area.
- [ ] Verify the volume icon controls the active PipeWire/PulseAudio-compatible sound service and survives reboot.
- [ ] Ensure the panel layout persists after logout, normal reboot, hard power loss, and a fresh user account.
- [ ] Fix the first-boot missing clock and incorrect system time behavior tracked in **#7**.

## Themes, colors, and icons

- [ ] Perform a complete visual audit of every Spaced theme.
- [ ] Fix minor foreground, background, border, selection, hover, disabled, warning, and accent-color inconsistencies in every theme.
- [ ] Verify text contrast and readability in GTK 2, GTK 3, GTK 4, MATE, Caja, Brisk, LightDM, Calamares, and common Flatpak applications.
- [ ] Replace low-resolution application, panel, device, folder, and status icons with scalable SVG or correctly sized high-resolution assets.
- [ ] Fix the especially poor external/removable/data-drive desktop icon.
- [ ] Verify icon-theme inheritance so missing icons fall back to a high-quality parent theme instead of pixelated assets.
- [ ] Rebuild icon caches during the ISO build and after theme package installation.
- [ ] Fix HiDPI scaling, tiny close/minimize controls, and mixed-resolution icon behavior tracked in **#6**.
- [ ] Make LibreOffice, Flatpaks, and other applications follow the selected theme as tracked in **#10**.
- [ ] Ensure theme selection persists after every reboot and power-loss scenario as tracked in **#12**.
- [ ] Unify the visual language across GRUB, Plymouth, Calamares, LightDM, the desktop, and recovery dialogs.

## Browser, application defaults, and desktop integration

- [ ] Fix HTTP, HTTPS, HTML, `xdg-open`, GIO, and GitHub CLI authentication links so they open Brave rather than Pluma.
- [ ] Apply the Brave Flatpak desktop ID (`com.brave.Browser.desktop`) as the correct default for every installed user.
- [ ] Ensure `BROWSER`/`GH_BROWSER` overrides are not required for normal desktop behavior.
- [ ] Include `gnome-keyring`, `dconf-cli`, `libcanberra-gtk3-module`, and any other required desktop-integration packages in the ISO.
- [ ] Verify Polkit prompts, keyring unlock, pinentry, portals, MIME associations, and Flatpak desktop integration.
- [ ] Audit every Spaced desktop entry for the correct Brisk category, icon, startup notification, keywords, and executable path.
- [ ] Keep the NVIDIA installer in **System Tools** and hide its post-reboot verifier from normal menus.

## Storage and Caja

- [ ] Add a safe **Open as Administrator** action to Caja.
- [ ] Make existing ext4 data drives accessible after reinstall when files are owned by an older numeric UID/GID.
- [ ] Provide a user-friendly migration or repair tool that changes only the intended old ownership and preserves `lost+found`, root-owned files, permissions, ACLs, and extended attributes.
- [ ] Verify removable and internal data drives mount with sensible user access through UDisks/Caja.
- [ ] Document recovery steps for drives that were created by a previous Spaced installation.

## Boot, installer, and release engineering

- [ ] Remove the QEMU-only `video=Virtual-1:1280x1024` argument from physical boot entries.
- [ ] Ensure normal boot, Safe Graphics, UEFI, legacy BIOS, and installed GRUB entries contain only appropriate arguments.
- [ ] Make GRUB detect other operating systems on the first installed boot as tracked in **#11**.
- [ ] Correct timezone and clock synchronization during live boot, installation, and first boot as tracked in **#7**.
- [ ] Verify Calamares preserves the correct desktop, panel, theme, user groups, LightDM, networking, sound, and Compiz configuration.
- [ ] Add automated checks for shell syntax, Python syntax, desktop files, executable modes, overlay paths, blacklists, session files, and initramfs contents.
- [ ] Add QEMU smoke tests for normal boot and Safe Graphics.
- [ ] Run clean physical install tests on NVIDIA, AMD, and Intel graphics where hardware is available.
- [ ] Test both a blank-disk install and an install beside another operating system.
- [ ] Build and publish `v7.26.4-rc2` only after the exact ISO passes the complete test matrix.
- [ ] Keep the PR and release as draft/prerelease until the clean physical install succeeds.
- [ ] Never commit ISO images or build caches to Git history; attach release images only as GitHub Release assets.

## Existing roadmap issues

- [ ] **#8 — Spaced Update Added to OS:** finish a first-party updater and define safe APT/Flatpak update behavior.
- [ ] **#9 — New torrent based repos:** research torrent distribution, cryptographic verification, and integration with Flatpak updates.
- [ ] **#14 — Screen Lock after Screen Saver?:** define and test the default lock-after-screensaver behavior.

## Release acceptance criteria

Spaced Linux 7.26.4 is ready to leave prerelease status only when:

- [ ] A clean physical install reaches LightDM and a stable MATE/Compiz desktop without manual repair.
- [ ] The NVIDIA installer completes from the GUI, offers a reboot dialog, and boots into the verified proprietary NVIDIA stack.
- [ ] A failed NVIDIA install automatically restores a bootable Nouveau configuration.
- [ ] Compiz starts reliably on proprietary NVIDIA and on the supported Nouveau/NVK fallback path.
- [ ] The MATE panel contains the intended controls, including a working volume icon and clock.
- [ ] No visible icons are obviously pixelated at normal DPI or HiDPI.
- [ ] Every shipped theme passes the color/contrast audit and persists after reboot.
- [ ] Brave opens web links and GitHub authentication flows by default.
- [ ] Existing data drives are accessible without unsafe blanket permission changes.
- [ ] Normal boot, Safe Graphics, QEMU, and clean physical installation tests all pass against the exact release ISO.
