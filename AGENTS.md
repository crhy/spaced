# Spaced Linux — Project Instructions

## Purpose

Spaced Linux 9.26: A Devuan Ceres-based distribution with a MATE desktop, Flatpak-primary application model, and Windows XP-style desktop layout.

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

## Release versioning

A release line is named for the calendar **month and two-digit year** it opens
in. `9.26` is September 2026, `8.26` is August 2026. The number before the dot
is a month, never a major version, so it never exceeds 12 and wraps: the
release after `12.26` is `1.27`, not `13.26`. A line keeps its name if it slips
a day past its month — `7.26.5` was published on 1 August 2026.

Two components sit below the line name:

- A **patch release** adds a third component, as in `9.26.1`. This is a new OS
  version. `VERSION`, `config/iso.yaml`, `overlays/etc/os-release`,
  `overlays/etc/lsb-release`, the Calamares branding, the GRUB entries and the
  live-build ISO name must all agree, and `scripts/check.sh` enforces that.
  `VERSION_CODENAME` is the version with the dots removed, so `9.26.1` becomes
  `9261`.
- A **Debian package revision** adds `-N`, as in `9.26.1-3`. It delivers fixes
  to installed systems through the APT repository without changing the OS
  version, because `packages/spaced-meta/DEBIAN/postinst` strips the revision
  before writing `/etc/os-release`. Use it for a fix that does not warrant a
  new ISO. `scripts/build-apt-repo.sh` refuses to republish different bytes
  under a version that is already published, so any content change needs a new
  revision.

## User Preferences

- Keep it lean, fast-booting, and responsive
- No systemd — sysvinit only
- Implement only what's asked; no feature creep
- Prefer bash scripts over inline code
- Progressive disclosure — reference files only when needed

## Commands

- Test config: `python3 -c "import glob, yaml; [yaml.safe_load(open(path)) for path in glob.glob('config/*.yaml')]"`
- Script syntax: `find scripts -name '*.sh' -exec bash -n {} +`
