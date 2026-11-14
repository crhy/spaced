# Spaced Linux 11.26.1

![The Spaced Linux 11.26.1 live desktop: dark theme, wallpaper, bottom panel and the live desktop icons](https://raw.githubusercontent.com/crhy/spaced/release/11.26.1/docs/releases/11.26.1/images/shot-desktop-dark.webp)

The first patch release of the 11.26 line: the same MATE desktop you know, with
dozens of security, safety and efficiency fixes underneath it. Reboot and
power-off no longer crash, an install that reuses your home partition keeps it,
updates refuse to unpack packages while the package system is unhealthy, and the
live USB doubles as a rescue stick.

<!--
Headline count, so "dozens" is honest: 41 commits between v11.26 and v11.26.1
(`git rev-list --count v11.26..v11.26.1` = 41), 31 changelog items in the
11.26.1 section of CHANGELOG.md (13 Fixes, 7 Safety and reliability, 4 Live USB
and installer, 7 Under the hood), 11 issue numbers (#303 #397 #406 #407 #408
#409 #412 #413 #414 #415 #11), plus 3 more items in the 11.26.1-2 package
revision. Hero image: docs/releases/11.26.1/images/shot-desktop-dark.webp,
taken from the released ISO in QEMU (images/README.md).
-->

## Restart your PC right after this update

**Save your work first.** 11.26.1 is a large update: it replaces the kernel and
the login service (elogind). Once the update finishes, apps can lose network
access and sound until you restart. If **Restart** in the menu asks for your
password or does nothing, open a terminal and run `sudo reboot`.

<!-- CHANGELOG.md:10-15 (11.26.1-2 "Known issue") and docs/releases/11.26.1/RELEASE-NOTES.md:12-16. Found on the one physical PC the update was applied to: docs/11.26.1-RELEASE-REVIEW.md "Not tested". -->

## New and improved apps

| | |
|---|---|
| ![Spaced Monitor 0.1.9 showing CPU, memory, GPU, disk and network cards above the process list](https://raw.githubusercontent.com/crhy/spaced/release/11.26.1/docs/releases/11.26.1/images/card-spaced-monitor.webp) | ![Spaced Welcome 0.1.22 first page: recommended essentials, suggested applications and version 0.1.22](https://raw.githubusercontent.com/crhy/spaced/release/11.26.1/docs/releases/11.26.1/images/card-spaced-welcome.webp) |
| **Spaced Monitor 0.1.9** - About/version, compact three-column hardware cards, double-click for a detailed view. Stop controls use a red X only for protected session or system processes and an orange X for ordinary ones. <!-- CHANGELOG.md:53-56 (#4, #5, #6); pinned by SHA-256 in config/external-artifacts.conf (SPACED_MONITOR_VERSION=0.1.9); window content read back out of the pixels in build/vm-tests/r01/spaced-linux-11.26.1-amd64/shot-spaced-monitor.ocr.txt -->
| **Spaced Welcome 0.1.22** - the reviewed recommended set is Spaced Bazaar, Brave, LibreOffice and VLC; audio, RGB, voice and game apps stay individually available, and the suggested-install button is highlighted without animation. <!-- CHANGELOG.md:57-60 (#11); pinned by SHA-256 (SPACED_WELCOME_VERSION=0.1.22, commit 72dcd21); "Version 0.1.22" is readable in the pixels: shot-spaced-welcome.ocr.txt -->
| ![Caja with solarsystem.jpg selected and its right-click menu open, showing Set as Wallpaper...](https://raw.githubusercontent.com/crhy/spaced/release/11.26.1/docs/releases/11.26.1/images/card-caja-set-wallpaper.webp) | ![Spaced Update 0.2.3 opened offline on the OS Release tab](https://raw.githubusercontent.com/crhy/spaced/release/11.26.1/docs/releases/11.26.1/images/card-spaced-update-os-release.webp) |
| **Caja: Set as Wallpaper…** - keeps a safe private copy of the picture, recommends crop or fit from the image and screen ratios, and lets you choose the placement. <!-- CHANGELOG.md:48-50 (#303); tests/test_set_wallpaper.py; the menu text "Set as Wallpaper..." was read back out of the pixels with tesseract (build/vm-tests/r01/spaced-linux-11.26.1-amd64/shot-caja-set-wallpaper.ocr.txt) -->
| **Spaced Update 0.2.3** - opens on the **OS Release** tab, reports cleanups truthfully, and shows the real solver error instead of hiding it. <!-- CHANGELOG.md:93-97 and 102-106; default tab set in overlays/usr/lib/spaced-linux/spaced-update.py:707; version and "No update check yet" readable in shot-spaced-update-os-release.ocr.txt -->

## Safety and reliability

- **Reboot and power-off no longer crash.** The upstream elogind fixes for the
  reboot-helper crash and the XML entity lookup failure are backported into
  `257.13-1+spaced11.26.1`. In a test VM the 11.26 image segfaulted in every
  reboot round; the 11.26.1 image rebooted five rounds and powered off with no
  segfault. <!-- CHANGELOG.md:107-111 (#409); docs/11.26.1-RELEASE-REVIEW.md test table: `.strata/out/v01-old.txt` `RESULT: FAIL elogind=257.13-1 rounds=5` vs `.strata/out/v01-new.txt` / `v05-reboot.txt` `RESULT: PASS elogind=257.13-1+spaced11.26.1 rounds=5`, `segfault=no`; tests/test_elogind_backport.py -->
- **An unhealthy APT transaction is stopped before it unpacks anything.** Failed
  solver output is preserved and displayed, dependency and dpkg state are
  checked before and after an update, and an APT transaction guard covers
  command-line upgrades. Repository publication now has to pass historical
  full-upgrade fixtures, so a dependency regression like #415 cannot silently
  come back. <!-- CHANGELOG.md:93-97 (#415); tests/test_update_recovery.py, tests/test_meta_postinst.py; build/11.26.1-apt-candidate.log -->
- **One cosmetic step can no longer block the next upgrade.** A failed LightDM
  settings migration, crash-directory creation, daemon core-limit append or
  Samba usershare tweak no longer leaves the desktop or the release metapackage
  unconfigured. <!-- CHANGELOG.md:98-101 (#415); tests/test_settings_postinst.py, tests/test_meta_postinst.py -->
- **A reused `/home` survives installation.** A separate or reused `/home` now
  reaches the installed `/etc/fstab`, and the post-write guard stops safely if
  the selected home vanished or became ambiguous. The live account is removed
  without its home directory whenever `/home` is a separate partition, so a
  "reuse my installation" run can no longer delete the previous system's files. <!-- CHANGELOG.md:129-132 (#413); commit 74d3ce5; a real Calamares run in a VM: `.strata/out/v02-new.txt` `RESULT: PASS fstab_home=UUID=b9c35053-… keep_olduser=ok keep_user=ok` vs the 11.26 image `.strata/out/v02-old.txt` `keep_user=LOST`; tests/test_calamares_home_reuse.py -->
- **No shared SSH host keys.** Installed systems no longer inherit the live
  image's host keys. <!-- CHANGELOG.md:133-137; commit 80ebf44 (f01-installer-safety: "must never delete a reused home or ship shared SSH host keys") -->
- **The signed update repository expires.** The generated `Release` carries
  `Valid-Until` 180 days after its `Date`, so a frozen or replayed copy of the
  archive is refused instead of trusted forever; the repository must be
  republished at least every 180 days. <!-- CHANGELOG.md:121-126; commit 47fcbdd; build/11.26.1-apt-candidate.log `PASS: Release expires on Wed, 12 May 2027 21:28:44 +0000`, `PASS: altered signed release metadata rejected`, `PASS: altered package payload rejected` -->
- **An interrupted NVIDIA driver install can be undone.** After a power loss or
  a stopped driver install the machine is no longer left with Nouveau blocked
  and no way back: **Restore Graphics** recognises the unfinished transaction,
  says the previous installation was interrupted and undoes the driver changes
  it had already made. <!-- CHANGELOG.md:112-116; commit d3e6553 (f19-nvidia-rollback, release blocker); tests/test_driver_recovery.py -->
- **A session guard keeps the desktop alive through a login-service update**
  (`11.26.1-2` package revision): an `elogind` upgrade used to stop and start
  the login service, dropping the running session and leaving Flatpak apps such
  as Brave without name resolution or sound until you restarted. <!-- CHANGELOG.md:16-25 (11.26.1-2); commit 28e9dc0; overlays/usr/lib/spaced-linux/spaced-policy-rc.d; tests/test_policy_rc_d.py -->
- **Daily maintenance runs on machines that are off at night:** `anacron` is
  installed, so crash-report pruning, log rotation and the other daily jobs run
  at the first boot after their due time. <!-- CHANGELOG.md:117-120; commit 6ee9a5e; live image check `PASS` for anacron in `.strata/out/v05-live.txt` -->

## Fixes you can see

- Desktop icons stay inside the current monitor's work area, including after a
  panel layout change and for hot-plugged monitors. <!-- CHANGELOG.md:43-44 (#406, #407, #412); tests/test_desktop_reliability.py, tests/test_external_desktop_boundaries.py -->
- `xkill` has its purpose-built cursor back, installed only as the Xcursor
  `pirate` action, so ordinary pointers are unchanged. <!-- CHANGELOG.md:45-47 (#414); tests/test_xkill_cursor.py; screenshot build/vm-tests/v03/spaced-linux-11.26.1-amd64/xkill.png -->
- A damaged Flatpak portal permission database is repaired at login without
  hiding unrelated Caja locations from applications. <!-- CHANGELOG.md:41-42 (#408); commit 59f236c; tests/test_portal_db_repair.py -->
- Easy Effects is hidden in Spaced Bazaar while Spaced uses PulseAudio, because
  its required PipeWire path is not supported in 11.26.1. <!-- CHANGELOG.md:51-52 (#397); overlays/etc/bazaar/blocklist.yaml, asserted by scripts/check.sh -->
- Login is quieter: no recovery-dialog loop when the desktop cannot start, no
  repeated Flatpak questions per source, and the display power watcher
  reconciles every five minutes instead of every thirty seconds and ends with
  the session. <!-- CHANGELOG.md:61-69; commits 0f9e955, 4b4707e; overlays/usr/local/bin/spaced-display-repair:234 `while sleep 300; do` -->
- A restarting theme monitor no longer re-themes the desktop forever: it is
  still restarted when it dies, but only the first monitor of a session
  restores the panel, dock, wallpaper and palette. <!-- CHANGELOG.md:70-73; commit 84fecab; tests/test_desktop_change_theme.py -->
- The NVIDIA startup report is quick and honest: it stops re-checking after one
  minute instead of possibly an hour, **Restore Graphics and Reboot** reports
  why recovery stopped, **Keep System Running** is remembered, and **Copy Log**
  keeps the failure reason. <!-- CHANGELOG.md:74-80; commit 3746667 -->
- `Ctrl+Alt+C` checks that a spreadsheet program exists before touching the
  audio, so a system without one reports that and keeps playing sound instead
  of staying muted. <!-- CHANGELOG.md:81-84; commit ce854a0; tests/test_audio_restore.py -->
- Three small desktop helpers straightened out: a shortcut that names a program
  in the current folder runs that file, the graphics report says "no Spaced
  session processes are running" instead of calling that a failed check, and a
  misused wallpaper dialog prints its usage. <!-- CHANGELOG.md:85-90; commit ce854a0; tests/test_desktop_helpers.py, tests/test_set_wallpaper.py -->

## The live USB is also a rescue stick

The stick carries GParted, TestDisk, PhotoRec, ddrescue, `smartctl`,
`cryptsetup`, `lvm2`, `ntfs-3g`, `exfatprogs` and `parted`, and a
`Live session passwords.txt` note on the live desktop states the live user and
root passwords. The rescue tools stay on the stick: the installer removes them
and updates do not pull them in, so an installed system does not get them -
including GParted, which earlier releases also installed to the disk. The note
and the live accounts disappear from an installed system.

<!-- CHANGELOG.md:144-152; commits 2fd8bef, d54f138, a1f4abc, 5a921a0; live image check `RESULT: PASS passed=35 failed=0` covering all twelve rescue tools (.strata/out/v05-live.txt); installer run `.strata/out/v02-new.txt` `rescue_tools_installed=none`. -->

| | |
|---|---|
| ![GParted on the live stick device /dev/sr0, 1.52 GiB, SpacedLinux11261](https://raw.githubusercontent.com/crhy/spaced/release/11.26.1/docs/releases/11.26.1/images/card-live-rescue-gparted.webp) | |
| **GParted on the live stick** - the released ISO shows the stick's own device (`/dev/sr0`, 1.52 GiB, `SpacedLinux11261`) with no pending operations. The `Live session passwords.txt` note is on the left of the full desktop shot, not in this crop. <!-- docs/releases/11.26.1/images/shot-live-rescue-gparted.png; window list build/vm-tests/r01/spaced-linux-11.26.1-amd64/shot-live-rescue-gparted.windows.txt; text read back with tesseract from the card pixels -->

## Efficiency, measured in a VM

Three cold boots of each ISO in the same KVM VM, runs interleaved old/new.
These are VM numbers, not a claim about any particular machine.

| measured (median of 3 boots) | 11.26 | 11.26.1 | result |
|---|---|---|---|
| `spaced-display-repair` wake-ups per 120 s idle | 27 | 0 | better |
| context switches/s while idle | 4886.5 | 4594.7 | −6.0 % |
| interrupts/s while idle | 1327.1 | 1251.1 | −5.7 % |
| ISO size | 1634871296 B | 1633140736 B | 1.7 MB smaller |
| boot time to a ready desktop | 14.15 s | 15.20 s | same (ranges overlap) |
| used memory after 60 s idle | 1081 MiB | 1072 MiB | same |
| idle CPU (60 s, 4 CPUs) | 7.66 % | 7.24 % | same |

<!-- All numbers: docs/releases/11.26.1/MEASUREMENTS.md (comparison table, "same"
where the three-run ranges overlap). The display-repair change is commit 0f9e955,
overlays/usr/local/bin/spaced-display-repair:234. -->

Nothing here is claimed as a boot-time or memory win: boot time, desktop-ready
time and memory measured **the same** within the run-to-run spread, and the idle
CPU row is "same" too. The idle numbers above were taken in a **live session**;
see the known limits below before reading anything into them.

<!-- Rule applied: metrics marked "same" in MEASUREMENTS.md are not presented as gains. -->

## Download and verify

- File: `spaced-linux-11.26.1-amd64.iso` - 1633140736 bytes (about 1.52 GiB)
- SHA-256: `937030fcb2103d5115ddda6d2e9ade497d239b1ff250352ee01bb34a734b1d6f`

```sh
sha256sum -c spaced-linux-11.26.1-amd64.iso.sha256
```

<!-- build/iso/spaced-linux-11.26.1-amd64.iso.sha256 and MEASUREMENTS.md ISO table; the GitHub release assets `spaced-linux-11.26.1-amd64.iso` (size 1633140736, digest sha256:937030…) and `spaced-linux-11.26.1-amd64.iso.sha256` were read back with `gh release view v11.26.1 -R crhy/spaced --json assets`. -->

## Updating from 11.26

Open **Spaced Update**, check **OS Release**, and install. Or in a terminal:

```sh
sudo apt update && sudo apt full-upgrade
```

Restart your PC right after this update: it replaces the kernel and the login
service (elogind), and apps can lose network access and sound until you
restart. The packages and the `257.13-1+spaced11.26.1` elogind set come from the
signed Spaced repository.

A follow-up package revision, **`11.26.1-2`**, adds the session guard described
above: later updates of the login service no longer interrupt a running desktop.
It arrives through Spaced Update and needs no new ISO - the ISO and the reported
release version are unchanged.

<!-- CHANGELOG.md:5-8 and 26-28 (11.26.1-2 needs no new ISO); the real upgrade transaction `.strata/out/v04-upgrade.txt` (`PASS: e: /etc/os-release VERSION is "11.26.1"`, `PASS: e: dpkg --audit prints nothing`, `PASS: e: no Spaced package is offered again (no upgrade loop, issue #209)`). -->

## Known limits - read before you judge the numbers

- **Occasional idle CPU spikes in the live session are under investigation.** In
  short trial boots the live desktop once idled at 17-24 % CPU, with
  `spaced-theme-monitor` receiving a flood of theme-change notifications. The six
  measured boots above did not show it (6-9 % on both 11.26 and 11.26.1), and an
  installed 11.26.1 PC checked on real hardware showed 0 % CPU and no reads from
  the theme monitor. We are reproducing it before changing anything.
  <!-- Source: MEASUREMENTS.md (idle CPU rows) + host check 2026-11-14; fix task x01. -->
- **The live session keeps reading the ISO** even when nothing is happening:
  about 280 MB through squashfs per 60 s of "idle" desktop, from short-lived
  bubblewrap/glycin image-decoding children of the panel. Both 11.26 and 11.26.1
  do this. <!-- docs/releases/11.26.1/MEASUREMENTS.md, "Idle desktop breakdown" -->
- **`dpkg --audit` is ~90× slower on the live image** (6.8-8.5 s instead of
  0.07 s). The cause is the base dpkg 1.23.11 → 1.23.12: one audit went from 11
  read syscalls to 1216, dragging 166 MB through squashfs. Not a Spaced bug. On an
  installed 11.26.1 PC (real hardware) the same command took 0.2-0.6 s.
  <!-- Source: dpkg --audit timed twice on an installed 11.26.1 PC, dpkg 1.23.12: 586 ms, 202 ms. --> <!-- docs/releases/11.26.1/MEASUREMENTS.md, "`dpkg --audit` deep dive" -->
- **Nearly all testing ran in QEMU or VirtualBox.** The update has been applied
  on one physical PC, which is how the restart requirement above was found; no
  real GPU matrix, multi-monitor setup or physical USB boot was tested. <!-- docs/11.26.1-RELEASE-REVIEW.md "Not tested"; docs/releases/11.26.1/RELEASE-NOTES.md -->
- **The interrupted NVIDIA driver rollback is covered by automated tests only.** <!-- docs/11.26.1-RELEASE-REVIEW.md; tests/test_driver_recovery.py -->
- **The 11.26 → 11.26.1 upgrade ran in a live session**, where `update-grub`
  cannot finish; every package step completed, but the upgraded system was never
  booted. <!-- docs/11.26.1-RELEASE-REVIEW.md test table: `RESULT: FAIL passed=12 failed=1`, the single failure being `grub-probe: error: failed to get canonical path of 'overlay'`; `.strata/out/v04-upgrade.txt` -->
- **Still open and important** (`docs/ROADMAP.md` High): the live image shares
  one set of SSH host keys; Spaced Update can wait with no Cancel button and can
  leave a root helper running after a timeout; a maintainer script can open a
  private home during an unattended update; NVIDIA's package repository stays
  enabled after a driver install. <!-- docs/ROADMAP.md (commit 41b9f83), as listed in docs/releases/11.26.1/RELEASE-NOTES.md -->

## Proof behind this release

The source gate runs 429 unit tests and three GTK integration tests; the signed
repository candidate passed payload, 157 runtime dependency, trust/tamper and
historical full-upgrade checks; the ISO passed four live boot smoke tests, 35
live-image checks and a five-round reboot loop.

<!-- CHANGELOG.md:32-37 (11.26.1 section) and docs/11.26.1-RELEASE-REVIEW.md "Test results" table (`.strata/out/v04-upgrade-test-runner-gate.txt` `Ran 429 tests … OK`, `Ran 3 tests … OK`; `build/11.26.1-apt-candidate.log`; `.strata/out/v05-kvm-bios.txt`, `v05-kvm-efi.txt`, `v05-vbox-bios.txt`, `v05-vbox-efi.txt`; `.strata/out/v05-live.txt` `RESULT: PASS passed=35 failed=0`; `.strata/out/v05-reboot.txt`). -->

Full change list: [CHANGELOG.md](https://github.com/crhy/spaced/blob/release/11.26.1/CHANGELOG.md).
Test evidence, including what was not tested:
[the release review](https://github.com/crhy/spaced/blob/release/11.26.1/docs/11.26.1-RELEASE-REVIEW.md).
Planned next: [docs/ROADMAP.md](https://github.com/crhy/spaced/blob/release/11.26.1/docs/ROADMAP.md).
Screenshots and how they were taken:
[docs/releases/11.26.1/images/README.md](https://github.com/crhy/spaced/blob/release/11.26.1/docs/releases/11.26.1/images/README.md).
