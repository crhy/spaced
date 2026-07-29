#!/usr/bin/env python3
"""Create the Spaced Linux release/polish issue set idempotently.

Run from any directory after authenticating GitHub CLI:

    python3 create-spaced-github-issues.py

Use --dry-run to preview without writing to GitHub.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import textwrap
import urllib.parse
from dataclasses import dataclass
from typing import Iterable


DEFAULT_REPO = "crhy/spaced"
TRACKER_TITLE = "Spaced Linux 7.26.4 RC2 master release checklist"


LABELS = {
    "priority:blocker": ("b60205", "Must be resolved before the next release candidate"),
    "priority:high": ("d93f0b", "High-priority release or usability work"),
    "priority:medium": ("fbca04", "Important polish or maintenance work"),
    "type:bug": ("d73a4a", "Something is broken or behaves incorrectly"),
    "type:enhancement": ("a2eeef", "New capability or substantial improvement"),
    "type:release": ("5319e7", "Release engineering and validation"),
    "area:nvidia": ("76b900", "NVIDIA installation and graphics stack"),
    "area:compiz": ("5b5bd6", "Compiz window manager and rendering"),
    "area:session": ("0e8a16", "LightDM, PAM, elogind, and desktop sessions"),
    "area:panel": ("1d76db", "MATE panel and indicators"),
    "area:theme": ("c5def5", "Themes, colors, and visual consistency"),
    "area:icons": ("bfdadc", "Icon quality, sizing, and inheritance"),
    "area:apps": ("0052cc", "Application defaults and desktop integration"),
    "area:storage": ("006b75", "Storage, ownership, mounting, and Caja"),
    "area:installer": ("7057ff", "Calamares and installed-system cleanup"),
    "area:boot": ("000000", "GRUB, initramfs, Safe Graphics, and startup"),
    "area:release": ("5319e7", "Testing, CI, release candidates, and publishing"),
    "area:audio": ("c2e0c6", "Sound stack and volume controls"),
}


@dataclass(frozen=True)
class ExistingIssue:
    number: int
    title: str
    category: str
    labels: tuple[str, ...]


@dataclass(frozen=True)
class PlannedIssue:
    title: str
    category: str
    labels: tuple[str, ...]
    problem: str
    work: tuple[str, ...]
    acceptance: tuple[str, ...]
    related: str = ""

    def body(self) -> str:
        work = "\n".join(f"- [ ] {item}" for item in self.work)
        acceptance = "\n".join(f"- [ ] {item}" for item in self.acceptance)
        related = f"\n\n## Related\n\n{self.related.strip()}" if self.related.strip() else ""
        return textwrap.dedent(
            f"""\
            ## Problem

            {self.problem.strip()}

            ## Work

            {work}

            ## Acceptance criteria

            {acceptance}{related}
            """
        ).strip() + "\n"


EXISTING_ISSUES = (
    ExistingIssue(2, "Nvidia/Radeon Drivers in Devuan", "NVIDIA and graphics", ("priority:blocker", "area:nvidia", "type:enhancement")),
    ExistingIssue(6, "Better Hidpi Support", "Themes, colors, and icons", ("priority:high", "area:theme", "area:icons", "type:bug")),
    ExistingIssue(7, "Clock way Off after Install, Clock missing from panel on first boot.", "Panel, sound, and first boot", ("priority:high", "area:panel", "area:installer", "type:bug")),
    ExistingIssue(8, "Spaced Update Added to OS", "Existing roadmap", ("priority:medium", "area:apps", "type:enhancement")),
    ExistingIssue(9, "New torrent based repos.", "Existing roadmap", ("priority:medium", "area:release", "type:enhancement")),
    ExistingIssue(10, "Apps are not following theming", "Themes, colors, and icons", ("priority:high", "area:theme", "area:apps", "type:bug")),
    ExistingIssue(11, "Grub doesn't show other OSes on initial boot(s)", "Boot, installer, and release", ("priority:high", "area:boot", "area:installer", "type:bug")),
    ExistingIssue(12, "Theming did not stick after reboot.", "Themes, colors, and icons", ("priority:high", "area:theme", "type:bug")),
    ExistingIssue(14, "Screen Lock after Screen Saver?", "Existing roadmap", ("priority:medium", "area:session", "type:enhancement")),
)


ISSUES = (
    PlannedIssue(
        "Finish hardened NVIDIA installer and physical validation",
        "NVIDIA and graphics",
        ("priority:blocker", "area:nvidia", "area:release", "type:bug"),
        "The hardened installer is implemented on draft PR #18, but it is not release-ready until the complete graphical install, reboot, verification, and recovery paths pass on physical hardware.",
        (
            "Run the GUI installer on the RTX 4070 Ti Super from a clean Nouveau/NVK state.",
            "Confirm the selected NVIDIA package/module flavor is appropriate for the detected GPU.",
            "Confirm progress, warnings, errors, logging, reboot-now, and reboot-later behavior.",
            "Test Restore Nouveau after a successful proprietary-driver installation.",
            "Record the exact package versions, kernel, module versions, renderer, and post-reboot results.",
        ),
        (
            "The installer completes without manual terminal commands.",
            "The reboot dialog appears only after every pre-reboot verification passes.",
            "The system reboots to a graphical LightDM/MATE/Compiz desktop using the NVIDIA driver.",
            "The recovery path restores a bootable Nouveau desktop.",
        ),
        "Umbrella issue #2 and draft PR #18.",
    ),
    PlannedIssue(
        "Guarantee exact kernel headers and DKMS prerequisites for driver installs",
        "NVIDIA and graphics",
        ("priority:blocker", "area:nvidia", "area:installer", "type:bug"),
        "A driver package can install while DKMS fails to produce a module when exact headers or build tools are missing. That can leave Nouveau blacklisted and the machine without a usable display driver.",
        (
            "Check the candidate for `linux-headers-$(uname -r)` before changing graphics configuration.",
            "Install exact headers, the header meta-package, DKMS, compiler/build tools, certificates, curl, mokutil, and PCI utilities from the app.",
            "Stop with a clear warning when any required package is unavailable.",
            "Include the matching header strategy in the ISO build and release tests.",
        ),
        (
            "The installer makes no graphics-stack changes when exact headers are unavailable.",
            "`/lib/modules/$(uname -r)/build/Makefile` exists before driver installation begins.",
            "The app reports the missing package and repository clearly to a nontechnical user.",
        ),
        "Draft PR #18.",
    ),
    PlannedIssue(
        "Remove live-only NVIDIA blacklists and stale graphics configuration after install",
        "NVIDIA and graphics",
        ("priority:blocker", "area:nvidia", "area:installer", "type:bug"),
        "Live-image safety rules and stale Xorg/modprobe files can persist after Calamares installation and block either Nouveau or NVIDIA on the installed system.",
        (
            "Inventory all NVIDIA and Nouveau rules under `/etc/modprobe.d`, `/lib/modprobe.d`, GRUB defaults, and Xorg configuration directories.",
            "Remove Spaced live-only NVIDIA blacklists from installed systems.",
            "Neutralize stale rules that blacklist NVIDIA before enabling the installed driver.",
            "Remove stale explicit Xorg device configuration so automatic detection can work.",
            "Back up any configuration changed by the driver installer and restore it during rollback.",
        ),
        (
            "No installed-system file blacklists NVIDIA after a verified successful install.",
            "Nouveau is disabled only by the final verified NVIDIA configuration.",
            "A rollback restores the previous working configuration exactly enough to boot graphically.",
        ),
        "Root cause observed during the failed NVIDIA 550 installation; draft PR #18.",
    ),
    PlannedIssue(
        "Verify NVIDIA modules and initramfs before offering reboot",
        "NVIDIA and graphics",
        ("priority:blocker", "area:nvidia", "area:boot", "type:bug"),
        "APT success alone does not prove that the NVIDIA modules were built for the running kernel or included in the boot image.",
        (
            "Verify `nvidia`, `nvidia_modeset`, `nvidia_uvm`, and `nvidia_drm` with `modinfo -k`.",
            "Run DKMS for the exact running kernel and capture the build log.",
            "Rebuild the initramfs and verify that the required NVIDIA modules are present inside it.",
            "Verify NVIDIA DRM modesetting configuration.",
            "Automatically roll back when any verification fails.",
        ),
        (
            "The reboot prompt cannot appear unless all four modules exist for the running kernel.",
            "The generated initramfs contains the expected NVIDIA module files.",
            "A failed verification leaves a bootable Nouveau/Mesa configuration.",
        ),
        "Draft PR #18.",
    ),
    PlannedIssue(
        "Add post-reboot NVIDIA, OpenGL, and Compiz verification with recovery",
        "NVIDIA and graphics",
        ("priority:blocker", "area:nvidia", "area:compiz", "type:bug"),
        "Pre-reboot checks cannot prove which driver, renderer, or window manager will actually run after hardware initialization.",
        (
            "Verify the NVIDIA PCI device is bound to the expected kernel driver.",
            "Verify `nvidia-smi` and loaded NVIDIA modules.",
            "Verify OpenGL is NVIDIA hardware rendering rather than NVK/Zink or llvmpipe.",
            "Verify MATE, Compiz, the panel, and Caja are running.",
            "Show a clear success report or a recovery dialog with Restore Nouveau.",
        ),
        (
            "A successful boot produces an understandable confirmation dialog.",
            "A failed check identifies the exact failed component.",
            "The user can restore Nouveau without typing recovery commands.",
        ),
        "Draft PR #18.",
    ),
    PlannedIssue(
        "Make Compiz renderer-aware and remove Marco runtime fallback",
        "NVIDIA and graphics",
        ("priority:blocker", "area:compiz", "area:nvidia", "type:bug"),
        "Compiz works with llvmpipe on the current NVK/Zink path but produced a black desktop with hardware NVK/Zink. Proprietary NVIDIA should use hardware OpenGL. Runtime fallback to Marco hides failures and violates the Compiz-first design.",
        (
            "Detect the active OpenGL renderer before launching Compiz.",
            "Use the software OpenGL workaround only for the known NVK/Zink case.",
            "Explicitly clear software-rendering overrides on proprietary NVIDIA and other working hardware renderers.",
            "Launch Compiz directly without a Marco runtime fallback.",
            "Keep only the Marco libraries/packages required by the Compiz GTK decorator.",
        ),
        (
            "Proprietary NVIDIA starts Compiz with hardware OpenGL.",
            "NVK/Zink starts Compiz through the known working software path until the upstream issue is resolved.",
            "No normal Spaced session silently switches to Marco.",
        ),
        "Draft PR #18.",
    ),
    PlannedIssue(
        "Add Secure Boot and MOK handling to the NVIDIA installer",
        "NVIDIA and graphics",
        ("priority:high", "area:nvidia", "area:boot", "type:enhancement"),
        "Unsigned DKMS modules may not load when Secure Boot is enabled. The current safe behavior is to stop, but normies need a complete guided path.",
        (
            "Detect Secure Boot before any graphics-stack change.",
            "Determine whether Devuan's packaged DKMS signing/MOK workflow can be automated safely.",
            "Provide clear firmware/MOK instructions when enrollment is required.",
            "Keep the current driver untouched when the secure path cannot be completed.",
        ),
        (
            "Secure Boot systems cannot be left with both Nouveau and NVIDIA unusable.",
            "Every required user action is explained before reboot.",
            "The installer can verify that the enrolled/signed module loads after reboot.",
        ),
        "Umbrella issue #2.",
    ),
    PlannedIssue(
        "Test NVIDIA install and recovery across supported GPU generations",
        "NVIDIA and graphics",
        ("priority:high", "area:nvidia", "area:release", "type:release"),
        "The installer must not be validated only on one Ada-generation desktop GPU.",
        (
            "Define the supported NVIDIA generation and driver-branch matrix.",
            "Test at least one modern open-module GPU and one older proprietary-module GPU when hardware is available.",
            "Test install, upgrade, rollback, kernel update, and Restore Nouveau.",
            "Document unsupported hardware and legacy-driver behavior.",
        ),
        (
            "The supported matrix is documented in the repository.",
            "Each supported class has a recorded successful install and recovery result.",
            "Unsupported devices receive a clear warning rather than a destructive attempt.",
        ),
        "Umbrella issue #2.",
    ),
    PlannedIssue(
        "Fix LightDM and elogind PAM session handoff",
        "Login and session",
        ("priority:blocker", "area:session", "type:bug"),
        "LightDM was terminated during the greeter-to-user handoff because the greeter PAM stack directly opened duplicate systemd/elogind sessions in addition to `common-session`.",
        (
            "Remove direct duplicate `pam_systemd.so` and `pam_elogind.so` session lines from the LightDM greeter PAM file.",
            "Retain the normal `common-session` elogind integration.",
            "Test repeated login, logout, lock, unlock, user switch, and reboot cycles.",
            "Encode the fix in the ISO overlay or build scripts rather than repairing it after install.",
        ),
        (
            "LightDM stays running through every login transition.",
            "The MATE session has a valid elogind seat/session.",
            "No duplicate session hooks appear in the final PAM configuration.",
        ),
    ),
    PlannedIssue(
        "Remove live LightDM and autologin settings during Calamares install",
        "Login and session",
        ("priority:blocker", "area:session", "area:installer", "type:bug"),
        "The live image's LightDM configuration can survive installation and conflict with the installed-system greeter, session sharing, or autologin policy.",
        (
            "Inventory `/etc/lightdm/lightdm.conf` and every file under `/etc/lightdm/lightdm.conf.d` in the live image.",
            "Remove live autologin configuration during Calamares cleanup.",
            "Install a dedicated installed-system configuration with MATE and `xserver-share=false`.",
            "Verify there is no live user reference after installation.",
        ),
        (
            "A clean install stops at the intended LightDM greeter.",
            "No live username or autologin password remains.",
            "The installed configuration is identical after a reboot.",
        ),
    ),
    PlannedIssue(
        "Remove unsupported X sessions and force MATE as the default",
        "Login and session",
        ("priority:blocker", "area:session", "area:installer", "type:bug"),
        "Cairo-Dock/Compiz, Cairo-Dock/Metacity, and generic LightDM Xsession entries can expose unsupported login paths and select the wrong session.",
        (
            "Remove unsupported session desktop files from the image.",
            "Keep only the supported MATE login session.",
            "Set `.dmrc` and AccountsService defaults for the installed user.",
            "Keep Cairo-Dock as a desktop component without shipping it as a login session.",
        ),
        (
            "LightDM offers only supported session choices.",
            "A new user logs into MATE without manual session selection.",
            "Cairo-Dock still launches inside the intended desktop configuration.",
        ),
    ),
    PlannedIssue(
        "Restore the canonical MATE panel layout for every user",
        "Panel, sound, and first boot",
        ("priority:blocker", "area:panel", "area:installer", "type:bug"),
        "The installed system can start without the intended MATE panel layout, leaving core desktop controls missing.",
        (
            "Define and version one canonical MATE panel layout.",
            "Ship it under `/usr/share/mate-panel/layouts` and set it as the default.",
            "Seed it for `/etc/skel` and ensure first-login initialization applies it once.",
            "Test fresh users and upgrades without repeatedly overwriting user customization.",
        ),
        (
            "Every fresh account receives the intended panel on first login.",
            "The panel survives logout and reboot.",
            "Existing customized users are not reset on every update.",
        ),
        "Related to existing issue #7.",
    ),
    PlannedIssue(
        "Restore the sound and volume icon in the notification area",
        "Panel, sound, and first boot",
        ("priority:blocker", "area:panel", "area:audio", "type:bug"),
        "The installed desktop currently has no visible sound/volume control in the notification area, which is a major usability failure for normal users.",
        (
            "Determine whether the intended control is the MATE volume applet, a status notifier, or another PipeWire/PulseAudio-compatible component.",
            "Install and autostart the required package/service.",
            "Add the control to the canonical panel layout.",
            "Verify mute, volume, device selection, and persistence after reboot.",
        ),
        (
            "A volume icon is visible on every fresh install and new user account.",
            "Changing volume and mute state works immediately.",
            "The icon remains present after logout, reboot, and panel restart.",
        ),
    ),
    PlannedIssue(
        "Make all intended MATE panel applets persist",
        "Panel, sound, and first boot",
        ("priority:high", "area:panel", "type:bug"),
        "The clock and other panel components have disappeared or failed to initialize after installation or reboot.",
        (
            "Audit the Brisk menu, clock, notification area, network indicator, workspace controls, volume control, and intended launchers.",
            "Verify every applet package and schema is installed.",
            "Ensure panel object IDs and positions are valid and deterministic.",
            "Test normal reboot, hard power loss, panel reset, and a second new user.",
        ),
        (
            "Every intended applet appears in the documented position.",
            "No applet disappears after a reboot or first-login race.",
            "The panel can recover cleanly from `mate-panel --reset`.",
        ),
        "Related to existing issue #7.",
    ),
    PlannedIssue(
        "Include required desktop integration packages in the ISO",
        "Applications and defaults",
        ("priority:high", "area:apps", "area:installer", "type:bug"),
        "The installed image was missing packages needed for keyring integration, dconf tooling, and GTK event sounds/modules.",
        (
            "Add `gnome-keyring`, `dconf-cli`, and `libcanberra-gtk3-module` to the appropriate package list.",
            "Verify Polkit, keyring, pinentry, GTK modules, portals, and Flatpak integration.",
            "Add build-time package-presence checks.",
        ),
        (
            "The packages are present on a clean install without manual APT commands.",
            "No missing-module warnings appear during normal desktop startup.",
            "GitHub/Brave/keyring and Polkit workflows operate normally.",
        ),
    ),
    PlannedIssue(
        "Keep Cairo-Dock available without shipping extra login sessions",
        "Login and session",
        ("priority:high", "area:session", "area:panel", "type:bug"),
        "Spaced needs Cairo-Dock as a desktop component, but its packaged login sessions create unsupported alternatives and can interfere with the intended MATE/Compiz session.",
        (
            "Keep the required Cairo-Dock packages and theme/launcher data.",
            "Remove Cairo-Dock login-session desktop files.",
            "Launch Cairo-Dock only through the intended MATE session/autostart path.",
            "Verify the dock starts once and uses the Spaced layout.",
        ),
        (
            "No Cairo-Dock session appears in LightDM.",
            "Cairo-Dock remains available in the normal Spaced desktop.",
            "The dock does not duplicate itself or start before the session is ready.",
        ),
    ),
    PlannedIssue(
        "Fix Brave URL handlers so links never open in Pluma",
        "Applications and defaults",
        ("priority:blocker", "area:apps", "type:bug"),
        "HTTP/HTTPS authentication links opened in Pluma even though the MIME database reported Brave as the default browser.",
        (
            "Audit XDG MIME, GIO, desktop-file, environment, and Flatpak export handling for HTTP, HTTPS, HTML, and XHTML.",
            "Set `com.brave.Browser.desktop` as the system default for new users.",
            "Remove stale Pluma associations from user and system MIME files.",
            "Test `xdg-open`, `gio open`, HTML files, GitHub CLI authentication, and links launched from GTK applications.",
        ),
        (
            "Every tested web link opens the Brave Flatpak.",
            "No `BROWSER` or `GH_BROWSER` workaround is needed for a fresh user.",
            "The association survives reboot and desktop-database updates.",
        ),
    ),
    PlannedIssue(
        "Audit and fix color inconsistencies across every Spaced theme",
        "Themes, colors, and icons",
        ("priority:high", "area:theme", "type:bug"),
        "All themes contain numerous small color inconsistencies that reduce polish and can harm contrast or readability.",
        (
            "Create a component/state audit covering normal, hover, active, selected, disabled, warning, error, success, focus, borders, shadows, and text.",
            "Review every shipped Spaced theme in GTK, MATE, Caja, Brisk, panel applets, dialogs, LightDM, and Calamares.",
            "Normalize accent colors and semantic colors within each theme while preserving each theme's identity.",
            "Capture before/after screenshots at normal DPI and HiDPI.",
        ),
        (
            "No unreadable or obviously mismatched color state remains in the audited applications.",
            "Every theme has a documented palette and screenshot set.",
            "Automated or scripted contrast checks cover the most important text/background pairs.",
        ),
        "Related to existing issues #10 and #12.",
    ),
    PlannedIssue(
        "Replace low-resolution desktop and panel icons with scalable assets",
        "Themes, colors, and icons",
        ("priority:high", "area:icons", "area:theme", "type:bug"),
        "Many icons throughout the desktop are visibly pixelated or too low resolution, especially at larger panel sizes or HiDPI.",
        (
            "Inventory application, device, panel, folder, status, MIME, action, and notification icons used by Spaced.",
            "Replace poor raster assets with SVGs or complete multi-resolution icon sets.",
            "Fix icon-theme inheritance and missing-size fallbacks.",
            "Rebuild icon caches during image construction and package installation.",
            "Test 1x, 1.5x, and 2x scaling.",
        ),
        (
            "No common desktop, panel, menu, notification, or device icon is visibly pixelated.",
            "Icon lookup does not fall back to an inappropriate tiny raster asset.",
            "The result is consistent across every shipped theme.",
        ),
        "Related to existing issue #6.",
    ),
    PlannedIssue(
        "Fix external and data-drive icon quality and theme inheritance",
        "Themes, colors, and icons",
        ("priority:high", "area:icons", "area:storage", "type:bug"),
        "Mounted external/data drives use an especially low-resolution desktop icon and may not inherit a suitable scalable device icon.",
        (
            "Identify the exact icon names requested by Caja/GIO for mounted internal, external, removable, and encrypted drives.",
            "Provide scalable icons or correct aliases in every Spaced icon theme.",
            "Verify inheritance to a high-quality parent theme.",
            "Test desktop, Caja sidebar, file chooser, and mount notifications.",
        ),
        (
            "Mounted drives display a sharp icon at all supported sizes and scale factors.",
            "The icon is consistent in Caja, the desktop, and dialogs.",
            "No broken symlink or missing cache entry is required to reproduce the fix.",
        ),
    ),
    PlannedIssue(
        "Add a safe Open as Administrator action to Caja",
        "Storage and Caja",
        ("priority:high", "area:storage", "area:apps", "type:enhancement"),
        "Caja currently lacks an obvious administrator action, making normal maintenance and recovery tasks unnecessarily difficult.",
        (
            "Evaluate `caja-admin` versus a maintained Caja action using Polkit/pkexec.",
            "Avoid launching an unrestricted root GUI session with the user's full environment.",
            "Support opening a folder and editing a file with clear authentication and warning text.",
            "Place the action in the expected context menu without clutter.",
        ),
        (
            "The action works from a standard user session after Polkit authentication.",
            "The implementation does not weaken X11, DBus, or filesystem permissions globally.",
            "Failure and cancellation are handled visibly.",
        ),
    ),
    PlannedIssue(
        "Handle existing data-drive ownership after reinstall or UID changes",
        "Storage and Caja",
        ("priority:high", "area:storage", "area:installer", "type:enhancement"),
        "After reinstall, an existing ext4 data drive can remain owned by the previous account's numeric UID/GID, leaving the new user unable to access personal files.",
        (
            "Detect mounted filesystems whose top-level personal content is owned by an orphaned numeric UID/GID.",
            "Offer an explicit migration tool that targets only the selected old UID/GID and selected filesystem.",
            "Preserve root-owned `lost+found`, special files, permissions, ACLs, xattrs, and mount boundaries.",
            "Provide a dry-run summary before changing ownership.",
        ),
        (
            "The user can regain access without a blanket recursive chmod/chown of unrelated files.",
            "The tool never crosses into another mounted filesystem.",
            "A log records every ownership migration.",
        ),
    ),
    PlannedIssue(
        "Unify GRUB, Plymouth, Calamares, LightDM, and desktop branding",
        "Themes, colors, and icons",
        ("priority:medium", "area:theme", "area:boot", "area:installer", "type:enhancement"),
        "Boot, installation, login, and desktop surfaces need one coherent Spaced visual system rather than separate color and asset choices.",
        (
            "Define a shared palette, logo treatment, typography, spacing, and asset-resolution standard.",
            "Audit GRUB, Plymouth, Calamares, LightDM, lock screen, recovery dialogs, and desktop defaults.",
            "Provide correctly sized assets for every stage and common display density.",
            "Verify no live-image branding or generic Debian branding survives installation.",
        ),
        (
            "Every stage is recognizably Spaced and visually consistent.",
            "Assets render sharply at common resolutions and HiDPI.",
            "A clean install contains no conflicting generic branding.",
        ),
    ),
    PlannedIssue(
        "Remove QEMU-only display arguments from physical boot entries",
        "Boot, installer, and release",
        ("priority:blocker", "area:boot", "type:bug"),
        "The normal live boot entry still contains a `video=Virtual-1:1280x1024` argument intended for QEMU, which should not be forced on physical hardware.",
        (
            "Remove the QEMU-specific video argument from the normal physical boot entry.",
            "Keep VM-specific display behavior in the QEMU test command or a dedicated VM entry only.",
            "Review normal and Safe Graphics arguments for physical NVIDIA, AMD, and Intel systems.",
        ),
        (
            "Physical boot entries contain no virtual-display connector names.",
            "QEMU tests still reach a usable resolution through test configuration.",
            "Normal and Safe Graphics both boot on the physical test machine.",
        ),
        "Draft PR #18.",
    ),
    PlannedIssue(
        "Clean all live-only packages and configuration after Calamares install",
        "Boot, installer, and release",
        ("priority:blocker", "area:installer", "area:session", "type:bug"),
        "The installed system retained live-only configuration, and cleanup currently removes only a subset of files and packages.",
        (
            "Create an explicit inventory of live-only packages, users, passwords, sudoers files, SSH settings, LightDM settings, autostarts, desktop icons, blacklists, and temporary state.",
            "Remove or replace each item in a deterministic Calamares cleanup step.",
            "Verify installed-system defaults after cleanup rather than relying on package side effects.",
            "Add automated post-install assertions.",
        ),
        (
            "A clean install contains no live user, live autologin, live password, live sudo rule, or live graphics blacklist.",
            "Only intended installed-system services and launchers remain.",
            "The cleanup is idempotent and logged.",
        ),
    ),
    PlannedIssue(
        "Audit all desktop entries and Brisk menu categories",
        "Applications and defaults",
        ("priority:medium", "area:apps", "area:panel", "type:bug"),
        "Spaced applications and helpers need consistent menu placement, icons, keywords, executable paths, and visibility rules.",
        (
            "Validate every Spaced `.desktop` file with `desktop-file-validate`.",
            "Review Categories, NoDisplay, OnlyShowIn, StartupNotify, Keywords, TryExec, and Icon fields.",
            "Keep the NVIDIA installer in System Tools and its post-reboot verifier hidden.",
            "Remove duplicate, dead, or generic installer entries.",
        ),
        (
            "Every Spaced application appears exactly once in the intended Brisk category.",
            "Hidden helpers never clutter normal menus.",
            "Every visible entry launches successfully on a clean install.",
        ),
    ),
    PlannedIssue(
        "Verify Flatpak portals, keyring, theming, and default-app integration",
        "Applications and defaults",
        ("priority:high", "area:apps", "area:theme", "type:bug"),
        "Flatpaks are central to Spaced's application strategy, so portals, keyring access, theming, MIME defaults, and desktop integration must work without manual repair.",
        (
            "Verify the required XDG desktop portals and MATE/GTK backends.",
            "Test file choosers, browser links, notifications, secret storage, audio, and removable-media access.",
            "Ensure shipped themes are available to Flatpak applications where technically possible.",
            "Test Brave and representative GTK/Qt Flatpaks.",
        ),
        (
            "Representative Flatpaks integrate with the desktop without missing portals or keyring prompts.",
            "Default-app and link handling match native applications.",
            "Theme behavior and known sandbox limitations are documented.",
        ),
        "Related to existing issues #9 and #10.",
    ),
    PlannedIssue(
        "Add automated validation for overlays, sessions, graphics rules, and desktop files",
        "Boot, installer, and release",
        ("priority:high", "area:release", "area:installer", "type:enhancement"),
        "Several release-breaking defects were simple file-content, mode, syntax, or cleanup errors that should be caught before building an ISO.",
        (
            "Run shell syntax checks on every shipped shell script.",
            "Compile-check every shipped Python file without writing bytecode into the source tree.",
            "Validate desktop files and executable modes.",
            "Assert supported X sessions, LightDM settings, PAM lines, panel layout, browser defaults, and graphics blacklists.",
            "Inspect the built SquashFS and installed test image for live-only leftovers.",
        ),
        (
            "The validation command fails on every known regression from the 7.26.4 testing cycle.",
            "Checks run locally and in GitHub Actions where practical.",
            "Release documentation names the exact command required before publishing an RC.",
        ),
    ),
    PlannedIssue(
        "Run the complete 7.26.4 RC2 installation and hardware test matrix",
        "Boot, installer, and release",
        ("priority:blocker", "area:release", "area:boot", "type:release"),
        "The next release candidate must be tested as the exact published ISO rather than inferred from a modified installed system.",
        (
            "Build a new ISO from the current branch after all release blockers are committed.",
            "Verify checksum and ensure the ISO/build cache are not added to Git history.",
            "Test QEMU normal boot and Safe Graphics.",
            "Test physical normal boot, Safe Graphics, Calamares install, first boot, NVIDIA installation, reboot, and recovery.",
            "Test AMD and Intel graphics where hardware is available.",
            "Test blank-disk and dual-boot/other-OS detection scenarios.",
        ),
        (
            "Every mandatory test has a recorded pass/fail result and log.",
            "The exact tested ISO is uploaded as `v7.26.4-rc2` prerelease assets.",
            "PR #18 remains draft until the complete physical matrix passes.",
        ),
        "Draft PR #18 and existing issues #7 and #11.",
    ),
    PlannedIssue(
        "Document NVIDIA installation, rollback, and SSH recovery",
        "Boot, installer, and release",
        ("priority:medium", "area:nvidia", "area:release", "type:enhancement"),
        "Even with automatic rollback, maintainers and advanced users need a concise recovery path for black screens, DKMS failures, and driver upgrades.",
        (
            "Document the GUI workflow and expected reboot/post-reboot checks.",
            "Document SSH recovery, Nouveau restoration, DKMS log locations, and blacklist inspection.",
            "Document Secure Boot limitations and supported hardware policy.",
            "Link the guide from the installer error dialog and repository README.",
        ),
        (
            "A user with SSH access can restore a graphical Nouveau boot from the documented steps.",
            "The guide matches the actual helper paths, logs, and package strategy.",
            "The recovery document is versioned with the installer.",
        ),
    ),
)


def run(command: list[str], *, input_text: str | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, input=input_text, text=True, capture_output=True)
    if check and result.returncode != 0:
        print(result.stdout, end="", file=sys.stdout)
        print(result.stderr, end="", file=sys.stderr)
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(command)}")
    return result


def gh_api(repo: str, method: str, path: str, payload: dict | None = None, *, check: bool = True) -> dict | list | None:
    command = ["gh", "api", "--method", method, path]
    input_text = None
    if payload is not None:
        command.extend(["--input", "-"])
        input_text = json.dumps(payload)
    result = run(command, input_text=input_text, check=check)
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return json.loads(result.stdout)


def ensure_auth() -> None:
    run(["gh", "--version"])
    run(["gh", "auth", "status"])


def load_existing(repo: str) -> dict[str, dict]:
    result = gh_api(repo, "GET", f"repos/{repo}/issues?state=all&per_page=100")
    assert isinstance(result, list)
    return {
        item["title"]: item
        for item in result
        if "pull_request" not in item
    }


def load_labels(repo: str) -> set[str]:
    result = gh_api(repo, "GET", f"repos/{repo}/labels?per_page=100")
    assert isinstance(result, list)
    return {item["name"] for item in result}


def ensure_labels(repo: str, dry_run: bool) -> None:
    existing = load_labels(repo)
    for name, (color, description) in LABELS.items():
        if name in existing:
            continue
        if dry_run:
            print(f"DRY-RUN create label: {name}")
            continue
        gh_api(
            repo,
            "POST",
            f"repos/{repo}/labels",
            {"name": name, "color": color, "description": description},
        )
        print(f"Created label: {name}")


def add_labels(repo: str, issue_number: int, labels: Iterable[str], dry_run: bool) -> None:
    label_list = list(labels)
    if dry_run:
        print(f"DRY-RUN label #{issue_number}: {', '.join(label_list)}")
        return
    gh_api(
        repo,
        "POST",
        f"repos/{repo}/issues/{issue_number}/labels",
        {"labels": label_list},
    )


def create_issue(repo: str, issue: PlannedIssue, dry_run: bool) -> dict:
    if dry_run:
        print(f"DRY-RUN create issue: {issue.title}")
        return {
            "number": 0,
            "title": issue.title,
            "html_url": "(dry-run)",
            "body": issue.body(),
        }
    created = gh_api(
        repo,
        "POST",
        f"repos/{repo}/issues",
        {
            "title": issue.title,
            "body": issue.body(),
            "labels": list(issue.labels),
        },
    )
    assert isinstance(created, dict)
    print(f"Created #{created['number']}: {issue.title}")
    return created


def tracker_body(records: list[tuple[str, dict]]) -> str:
    grouped: dict[str, list[dict]] = {}
    for category, item in records:
        grouped.setdefault(category, []).append(item)

    lines = [
        "# Spaced Linux 7.26.4 RC2 master release checklist",
        "",
        "This tracker is generated by `create-spaced-github-issues.py`.",
        "The committed human-readable checklist is `SPACED-TODO.md`.",
        "",
        "Draft implementation PR: #18",
        "",
    ]

    for category in sorted(grouped):
        lines.extend([f"## {category}", ""])
        for item in sorted(grouped[category], key=lambda value: (value.get("number", 0), value["title"])):
            number = item.get("number", 0)
            url = item.get("html_url", "")
            if number:
                lines.append(f"- [ ] [#{number} — {item['title']}]({url})")
            else:
                lines.append(f"- [ ] {item['title']}")
        lines.append("")

    lines.extend(
        [
            "## Final release gate",
            "",
            "- [ ] Exact RC2 ISO passes QEMU normal and Safe Graphics boot.",
            "- [ ] Exact RC2 ISO passes clean physical installation.",
            "- [ ] NVIDIA GUI install, reboot, proprietary OpenGL, Compiz, and Restore Nouveau all pass.",
            "- [ ] MATE panel includes a working volume icon, clock, and intended indicators.",
            "- [ ] Theme and icon audits pass at normal DPI and HiDPI.",
            "- [ ] PR #18 is moved out of draft only after all mandatory physical tests pass.",
            "",
        ]
    )
    return "\n".join(lines)


def upsert_tracker(repo: str, existing: dict[str, dict], records: list[tuple[str, dict]], dry_run: bool) -> None:
    body = tracker_body(records)
    current = existing.get(TRACKER_TITLE)
    if dry_run:
        action = "update" if current else "create"
        print(f"DRY-RUN {action} tracker: {TRACKER_TITLE}")
        return

    payload = {
        "title": TRACKER_TITLE,
        "body": body,
        "labels": ["priority:blocker", "area:release", "type:release"],
    }
    if current:
        updated = gh_api(repo, "PATCH", f"repos/{repo}/issues/{current['number']}", payload)
        assert isinstance(updated, dict)
        print(f"Updated tracker #{updated['number']}: {updated['html_url']}")
    else:
        created = gh_api(repo, "POST", f"repos/{repo}/issues", payload)
        assert isinstance(created, dict)
        print(f"Created tracker #{created['number']}: {created['html_url']}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=DEFAULT_REPO, help="GitHub repository in owner/name form")
    parser.add_argument("--dry-run", action="store_true", help="Preview without changing GitHub")
    args = parser.parse_args()

    ensure_auth()
    ensure_labels(args.repo, args.dry_run)
    existing = load_existing(args.repo)
    records: list[tuple[str, dict]] = []

    for item in EXISTING_ISSUES:
        current = next((value for value in existing.values() if value.get("number") == item.number), None)
        if current is None:
            print(f"WARNING: expected existing issue #{item.number} was not found", file=sys.stderr)
            continue
        add_labels(args.repo, item.number, item.labels, args.dry_run)
        records.append((item.category, current))
        print(f"Using existing #{item.number}: {current['title']}")

    for issue in ISSUES:
        current = existing.get(issue.title)
        if current:
            print(f"Skipping existing #{current['number']}: {issue.title}")
            add_labels(args.repo, current["number"], issue.labels, args.dry_run)
            records.append((issue.category, current))
            continue
        created = create_issue(args.repo, issue, args.dry_run)
        records.append((issue.category, created))
        if not args.dry_run:
            existing[issue.title] = created

    upsert_tracker(args.repo, existing, records, args.dry_run)
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
