# Spaced Linux — Project Instructions

## Purpose

Spaced Linux 8.26.6: A Devuan Ceres-based distribution with a MATE desktop, Flatpak-primary application model, and Windows XP-style desktop layout.

## Key Architecture

- **Base**: Devuan Excalibur → dist-upgrade to Ceres (rolling, sysvinit)
- **Desktop**: MATE + Compiz
- **Apps**: Flatpak/Flathub for user applications, native debs for system tools
- **Build**: KVM VM for development, live-build or manual rootfs for ISO
- **Installer**: Calamares

## Desktop Layout

Single panel (bottom by default; top for Android and Mac OS X, which also
enable the cairo-dock at the bottom). Windows XP style:
```
[Brisk Menu] [Window List] ........ [Volume] [Notification Area] [Clock] [Show Desktop]
```
The panel applet set is identical for every theme (see `docs/matepanel.md`).

## User Preferences

- Keep it lean, fast-booting, and responsive
- No systemd — sysvinit only
- Implement only what's asked; no feature creep
- Prefer bash scripts over inline code
- Progressive disclosure — reference files only when needed

## Commands

- Test config: `python3 -c "import glob, yaml; [yaml.safe_load(open(path)) for path in glob.glob('config/*.yaml')]"`
- Script syntax: `find scripts -name '*.sh' -exec bash -n {} +`
