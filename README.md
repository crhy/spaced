# Spaced Linux 6.26

An extremely user-friendly and comprehensively useful lightweight version of Devuan. Built on the rolling release version of Devuan (Ceres/Excalibur), with a MATE desktop, monochrome theming, and WinXP-style bottom panel.

## Features

- **Base**: Devuan Ceres (systemd-free, rolling release, sysvinit)
- **Desktop**: MATE with WinXP-style single bottom panel
- **Theme**: Spaced-Dark — pure monochrome UI
- **Applications**: Flatpak/Flathub integrated
- **Wallpaper**: SpacedBack.png via MATE desktop management
- **Installer**: Calamares

## Quick Start

### Prerequisites

- Devuan/Debian host
- Tools: `live-build`, `qemu-system-x86_64`, `xorriso`

### Build ISO

```bash
git clone https://github.com/crhy/spaced.git
cd spaced
make release
```

### Build with Docker

```bash
docker build -t spaced-linux-builder .
docker run --privileged -v $(pwd)/build:/build spaced-linux-builder
```

## Version

6.26
