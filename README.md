<p align="center">
  <a href="https://spacedlinux.com">
    <img src="branding/spaced-icon-fancy.png" alt="Spaced Linux logo" width="190">
  </a>
</p>

<h1 align="center">Spaced Linux 8.26</h1>

<p align="center"><strong>Spaced. Polished. Agile. Compiz. Efficient. Devuan.</strong></p>

<p align="center">
  A beautiful, familiar, systemd-free Linux desktop for beginners, power users,<br>
  and anyone who wants their computer to feel like their own.
</p>

<p align="center">
  <a href="https://spacedlinux.com"><strong>Website</strong></a> ·
  <a href="https://github.com/crhy/spaced/releases"><strong>Download releases</strong></a> ·
  <a href="https://github.com/crhy/spaced/issues"><strong>Issues</strong></a> ·
  <a href="docs/DESIGN.md"><strong>Design</strong></a> ·
  <a href="#support-spaced-linux"><strong>Support</strong></a>
</p>

<p align="center">
  <img alt="Devuan Ceres" src="https://img.shields.io/badge/base-Devuan%20Ceres-4b5563">
  <img alt="MATE desktop" src="https://img.shields.io/badge/desktop-MATE-8bc34a">
  <img alt="Compiz" src="https://img.shields.io/badge/window%20manager-Compiz-5b5bd6">
  <img alt="Init system" src="https://img.shields.io/badge/init-sysvinit-555555">
  <img alt="Architecture" src="https://img.shields.io/badge/architecture-amd64-2563eb">
  <img alt="Release" src="https://img.shields.io/badge/release-8.26-0ea5e9">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-black">
</p>

<p align="center">
  <a href="website/assets/screenshots/desktop-hero.webp">
    <img src="website/assets/screenshots/desktop-hero.webp" alt="Spaced Linux desktop" width="100%">
  </a>
</p>

## Linux that feels familiar. Freedom that goes deeper.

Spaced Linux is a polished desktop distribution built on **Devuan Ceres**, using **sysvinit**, **MATE**, and **Compiz**. It welcomes first-time Linux users without hiding the system from experienced users who want to inspect, customize, automate, and rebuild it.

The desktop begins with a familiar layout: a clear application menu, conventional windows, readable controls, and tools placed where people expect them. Beneath that approachable surface is a lean Devuan base, a deeply configurable Compiz desktop, Flatpak and Flathub integration, a graphical Calamares installer, and a reproducible live-build workflow.

Compiz is not an optional novelty. It is the primary window manager and compositor, providing smooth animation, flexible workspace behavior, window rules, accessibility features, and the visual personality that makes Spaced Linux feel alive. Marco remains available as a dependable fallback.

## Spaced Linux in action

These are real Spaced Linux desktop sessions—not wallpaper mockups. Click any image to view it at full size.

<table>
  <tr>
    <td width="50%" align="center">
      <a href="website/assets/screenshots/desktop-compiz.webp"><img src="website/assets/screenshots/desktop-compiz.webp" alt="Spaced Linux Compiz workspace cube with a terminal"></a><br>
      <sub><strong>Compiz-first desktop</strong> — Workspaces, accessibility, motion, and organization are part of the core experience.</sub>
    </td>
    <td width="50%" align="center">
      <a href="website/assets/screenshots/desktop-welcome.webp?v=8.26"><img src="website/assets/screenshots/desktop-welcome.webp?v=8.26" alt="Welcome to Spaced Linux first-run application"></a><br>
      <sub><strong>Friendly first run</strong> — Start installing software or open the browser from one clear welcome screen.</sub>
    </td>
  </tr>
  <tr>
    <td width="50%" align="center">
      <a href="website/assets/screenshots/desktop-bazaar.webp"><img src="website/assets/screenshots/desktop-bazaar.webp" alt="Bazaar application store running on Spaced Linux"></a><br>
      <sub><strong>Modern applications</strong> — Flatpak and Flathub provide current software without dependency chaos.</sub>
    </td>
    <td width="50%" align="center">
      <a href="website/assets/screenshots/desktop-theme-cube-dark.webp"><img src="website/assets/screenshots/desktop-theme-cube-dark.webp" alt="Spaced Linux dark coordinated theme displayed across the Compiz workspace cube"></a><br>
      <sub><strong>Coordinated themes</strong> — GTK, icons, wallpaper, panels, and Compiz presentation move together.</sub>
    </td>
  </tr>
  <tr>
    <td width="50%" align="center">
      <a href="website/assets/screenshots/desktop-macos.webp"><img src="website/assets/screenshots/desktop-macos.webp" alt="Spaced Linux macOS-style themed desktop"></a><br>
      <sub><strong>A familiar favorite</strong> — The macOS-inspired theme is one of the many coordinated Spaced Linux desktop looks.</sub>
    </td>
    <td width="50%" align="center">
      <a href="website/assets/screenshots/desktop-ai-tools.webp"><img src="website/assets/screenshots/desktop-ai-tools.webp" alt="Spaced Linux running the Voice2Text local speech-to-text application"></a><br>
      <sub><strong>Private AI</strong> — Voice2Text transcribes speech locally on-device, part of the flatpak-driven AI workflow.</sub>
    </td>
  </tr>
  <tr>
    <td width="50%" align="center">
      <a href="website/assets/themes/theme-win11dark.webp"><img src="website/assets/themes/theme-win11dark.webp" alt="Spaced Linux Windows 11 dark themed desktop"></a><br>
      <sub><strong>Windows 11 dark</strong> — A modern dark look inspired by Windows 11, coordinated across GTK, icons, and panels.</sub>
    </td>
    <td width="50%" align="center">
      <a href="website/assets/themes/theme-winxp.webp"><img src="website/assets/themes/theme-winxp.webp" alt="Spaced Linux Windows XP themed desktop"></a><br>
      <sub><strong>Windows XP</strong> — A nostalgic Windows XP-style desktop that stays fast and familiar.</sub>
    </td>
  </tr>
</table>

## Why beginners feel at home

| Feature | Benefit |
|---|---|
| **Familiar desktop** | A classic desktop workflow avoids the learning curve of unfamiliar shells. |
| **Graphical installation** | Calamares provides a clear installation path for BIOS and UEFI systems. |
| **Useful defaults** | Networking, audio controls, archives, editing, document viewing, and system utilities are ready immediately. |
| **Modern applications** | Flatpak and Flathub provide current desktop apps without destabilizing the base system. |
| **Coordinated themes** | One choice can change the GTK theme, icons, folder colors, wallpaper, panel layout, and optional dock together. |
| **Safe fallback** | Marco is available when Compiz is unsuitable for a GPU, VM, or specialized workflow. |

## Why advanced users keep control

| Feature | Benefit |
|---|---|
| **Systemd-free architecture** | Devuan Ceres and sysvinit keep service management conventional, understandable, and scriptable. |
| **APT plus Flatpak** | Use native packages for the operating system and sandboxed apps for fast-moving desktop software. |
| **Deep Compiz configuration** | Tune effects, window rules, workspaces, keybindings, accessibility, and compositor behavior. |
| **Reproducible builds** | The repository contains the live-build configuration, package selection, overlays, scripts, and QEMU targets used to make the ISO. |
| **Plain-text configuration** | Themes, package groups, desktop defaults, and automation remain inspectable and version controlled. |
| **A practical customization base** | Fork it, rebuild it, replace the artwork, alter package groups, or turn it into another focused distribution. |

## A desktop with range

Spaced Linux combines a modern system with visual ideas from the best desktop eras. Its theme collection can evoke classic Windows, macOS, Android, Linux Mint, GeoWorks, or the distinctive monochrome Spaced identity without becoming a fragile pile of unrelated tweaks.

<p align="center">
  <a href="website/assets/screenshots/desktop-themes-current.webp">
    <img src="website/assets/screenshots/desktop-themes-current.webp" alt="Spaced Linux coordinated theme collection" width="100%">
  </a>
</p>

## Core components

- **Base:** Devuan Ceres (unstable), rolling release
- **Init:** sysvinit
- **Desktop:** MATE
- **Primary window manager:** Compiz
- **Fallback window manager:** Marco
- **File manager:** Caja
- **Application menu:** Brisk Menu
- **Display manager:** LightDM GTK Greeter
- **Installer:** Calamares
- **Icons:** Spaced overlays based on Papirus
- **Application delivery:** APT plus Flatpak/Flathub
- **Target architecture:** amd64

## Download Spaced Linux

Download the ISO and its matching checksum from the [Spaced Linux releases page](https://github.com/crhy/spaced/releases).

Verify the download on Linux:

```bash
sha256sum -c spaced-linux-8.26-amd64.iso.sha256
```

Test release images in a virtual machine or on non-critical hardware before adopting them for daily use.

## Build Spaced Linux

A Devuan- or Debian-based build host is recommended.

```bash
git clone https://github.com/crhy/spaced.git
cd spaced
make deps
make release
```

The completed ISO is written beneath:

```text
build/iso/
```

### Test in QEMU

```bash
make iso-test
```

### Useful targets

```bash
make check
make help
make deps
make iso-build
make iso-test
make vm-start
make release
make clean
make cache-clean
```

QEMU defaults to a 1440×900 GTK window and forwards guest SSH to port `2222`.

## Support Spaced Linux

Spaced Linux is an independent project. Donations help cover hosting, testing, hardware, development time, and future releases.

<table>
  <tr>
    <td width="50%" align="center" valign="top">
      <a href="https://mempool.space/address/bc1q3kgsasmwyc2knfa8snzqstr7m983sxwleql7l2">
        <img src="website/assets/donate-bitcoin.png" alt="Donate Bitcoin to Spaced Linux" width="340">
      </a><br>
      <strong>Bitcoin</strong><br>
      <code>bc1q3kgsasmwyc2knfa8snzqstr7m983sxwleql7l2</code>
    </td>
    <td width="50%" align="center" valign="top">
      <a href="https://venmo.com/u/green-jacket">
        <img src="website/assets/donate-venmo.png" alt="Donate to Spaced Linux with Venmo" width="340">
      </a><br>
      <strong>Venmo</strong><br>
      <code>@green-jacket</code>
    </td>
  </tr>
</table>

Thank you for helping keep an independent, polished, systemd-free desktop available to everyone.

## Project status

The current development line is **8.26**. Spaced Linux is an independent community project under active development.

## Contributing

### NVIDIA Recovery Guide

Spaced Linux includes a verified, transactional NVIDIA driver installer with automatic rollback, pre-reboot verification, and post-reboot desktop checks. For installation steps, SSH recovery procedures, DKMS troubleshooting, Secure Boot limitations, and the full error-code reference see:

- [docs/NVIDIA-RECOVERY.md](docs/NVIDIA-RECOVERY.md)

## Contributing

Bug reports, documentation improvements, Compiz refinements, theme work, package suggestions, hardware testing, accessibility improvements, and build fixes are welcome.

Open an [issue](https://github.com/crhy/spaced/issues) or submit a pull request describing what changed and how it was tested.

## Acknowledgements

Spaced Linux builds on the work of the Devuan, Debian, MATE, Compiz, Calamares, Flatpak, Papirus, and broader free-software communities.

## License

Project-specific build configuration and code are released under the [MIT License](LICENSE). Upstream packages, artwork, themes, fonts, and components retain their respective licenses.
