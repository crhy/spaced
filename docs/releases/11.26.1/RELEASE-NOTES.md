# Spaced Linux 11.26.1

Spaced Linux 11.26.1 is the first patch release of the 11.26 line. It fixes the
crash that hit reboot and power-off, keeps a reused home partition through
installation, refuses to unpack packages while the package system is unhealthy,
and turns the live USB into a rescue stick.

**Restart your PC right after this update.** 11.26.1 is a large update: it
replaces the kernel and the login service (elogind). Save your work before you
start. Once the update finishes, apps can lose network access and sound until
you restart. If **Restart** in the menu asks for your password or does nothing,
open a terminal and run `sudo reboot`.

## Highlights

- **An install that reuses your home keeps it.** A separate or reused `/home`
  now reaches the installed `/etc/fstab`, and the live account is removed
  without its home directory (#413).
- **Reboot and power-off no longer crash.** Backported elogind patches fix the
  reboot-helper segfault: five reboot rounds and a power-off in a test VM show
  no crash, where the 11.26 image crashed in every round (#409).
- **Safer updates.** A failed dependency solve is shown instead of hidden, an
  APT guard refuses to unpack while dependencies or dpkg state are unhealthy,
  and a cosmetic post-install step cannot block the next upgrade (#415).
- **The live USB is a rescue system.** GParted, TestDisk, PhotoRec, ddrescue,
  `smartctl`, `cryptsetup`, `lvm2`, `ntfs-3g`, `exfatprogs` and `parted` are on
  the stick with a `Live session passwords.txt` note; the installer removes them.
- **Daily maintenance runs on machines that are off at night** — `anacron` runs
  the daily jobs at the first boot after their due time.
- **Login is quieter:** no thirty-second display-power wake-ups, no leftover
  monitors after logout, no recovery-dialog loop, no repeated Flatpak questions.
- **The signed update repository expires** 180 days after it was published, so a
  frozen or replayed copy of the archive is refused instead of trusted forever.
- Icons stay inside the current monitor's work area (#406, #407, #412), `xkill`
  has its cursor back (#414), Caja gains **Set as Wallpaper…** (#303), Easy
  Effects is hidden while Spaced uses PulseAudio (#397), a damaged Flatpak
  portal database is repaired at login (#408), and Monitor 0.1.9 and Welcome
  0.1.22 are pinned by exact archive digest.

## Download and verify

- File: `spaced-linux-11.26.1-amd64.iso` (1633140736 bytes, about 1.52 GiB)
- SHA-256: `937030fcb2103d5115ddda6d2e9ade497d239b1ff250352ee01bb34a734b1d6f`

```sh
sha256sum -c spaced-linux-11.26.1-amd64.iso.sha256
```

## Updating from 11.26

Open **Spaced Update**, check **OS Release**, and install. Or in a terminal:

```sh
sudo apt update && sudo apt full-upgrade
```

Restart your PC right after this update: it replaces the kernel and the login
service (elogind), and apps can lose network access and sound until you
restart. If **Restart** in the menu asks for your password or does nothing, open
a terminal and run `sudo reboot`. The packages and the
`257.13-1+spaced11.26.1` elogind set come from the signed Spaced repository.

A follow-up package revision, `11.26.1-2`, adds a session guard: later updates
of the login service no longer interrupt a running desktop. It arrives through
Spaced Update and needs no new ISO.

## Known limits

- Nearly all testing ran in QEMU or VirtualBox. The update has been applied on
  one physical PC, which is how the restart requirement above was found; no real
  GPU matrix, multi-monitor setup or physical USB boot was tested.
- The interrupted NVIDIA driver rollback is covered by automated tests only.
- The 11.26 → 11.26.1 upgrade ran in a live session, where `update-grub` cannot
  finish; every package step completed, but the upgraded system was never booted.
- The `xkill` cursor and the Spaced Monitor stop buttons were checked in live
  screenshots. Icon placement on multiple monitors and the Welcome button have
  not been checked by eye.
- Still open and important (`docs/ROADMAP.md` High): the live image shares one
  set of SSH host keys; Spaced Update can wait with no Cancel button and can
  leave a root helper running after a timeout; a maintainer script can open a
  private home during an unattended update; NVIDIA's package repository stays
  enabled after a driver install.

Full change list: [CHANGELOG.md](../../../CHANGELOG.md). Planned next:
[docs/ROADMAP.md](../../../docs/ROADMAP.md). Test evidence, including what was
not tested: [the release review](../../11.26.1-RELEASE-REVIEW.md).
