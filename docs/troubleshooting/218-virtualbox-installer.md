# #218 — VirtualBox live installer does nothing / session frozen (investigation only)

Investigation date: 2026-09-14. Source-only investigation; no code or config
was changed. All paths are relative to the repository root unless absolute.
Line numbers refer to the checkout at `1f42d76` (post-9.26.2-2).

Symptom (issue #218, Spaced Linux 9.26.2 live ISO in Oracle VirtualBox): the
"Install Spaced Linux" desktop launcher does nothing, and "the entire VM was
locked up, nothing was clickable or selectable". The same reporter saw a
"Network Servers" icon on the VirtualBox live desktop that does not appear on
their physical install. The published 9.26.2 evidence lists only BIOS, UEFI
and 4K QEMU smoke tests
(`docs/9.26.2-ISSUE-STATUS.md:111-114`).

## 1. Coverage: what the VirtualBox smoke test checks, and whether it could be skipped

The VirtualBox smoke script is `scripts/vm/virtualbox/smoke-iso.sh`. What it
does, in order:

- Creates a headless VM (`VBoxManage createvm`, lines 100-106) with
  `--graphicscontroller vboxsvga --accelerate-3d off` (lines 110-115), 2048 MiB
  / 2 CPUs by default (lines 12-13), NAT with host-forwarded SSH (line 115),
  and the ISO as a SATA DVD (lines 116-118).
- Polls until SSH answers (lines 54-63, 121), then runs
  `scripts/vm/live-desktop-probe.py` inside the guest over SSH as root
  (`desktop_is_ready`, lines 65-75).
- The probe (`scripts/vm/live-desktop-probe.py:23-55`) requires `mate-session`,
  `mate-panel`, `caja` and `compiz` running as user `user`, requires the EWMH
  `_NET_SUPPORTING_WM_CHECK` window to be Compiz, requires a working GLX
  renderer (lines 71-73), and checks OS identity/version.
- Finally it takes a VirtualBox screenshot and passes only if the PNG is at
  least 32 KiB, i.e. the wallpaper painted rather than a black frame
  (`capture_desktop`, lines 77-90; report assembly, lines 129-144).

What it does **not** do: launch the installer. There is no `calamares`
invocation anywhere in the script, no synthetic click on the desktop launcher,
and no check of `/usr/local/bin/install-spaced-linux`. It proves "live SSH +
painted MATE/Compiz desktop", nothing more. A broken installer launcher passes
this gate silently.

Where it sits in the gates:

- `Makefile:161` — `iso-smoke` aggregates `iso-smoke-kvm`,
  `iso-smoke-kvm-efi`, `iso-smoke-virtualbox` (line 175-177) and
  `iso-smoke-virtualbox-efi` (lines 179-181).
- `Makefile:226-228` — `release` runs only `release-preflight` (which is
  `check` + `scripts/release-preflight.sh`, lines 216-224), then `clean` and
  `lb-build`. No smoke test of any kind is in the release path.
- `.github/workflows/monthly-iso.yml:74-81` — CI runs `make iso-smoke-kvm`,
  `make iso-smoke-kvm-efi`, `make iso-smoke-kvm-4k` only. No VirtualBox target
  runs in CI.
- `.github/workflows/source-checks.yml` — only `make check`, the release
  identity test, and the site build.

So the VirtualBox smoke test is **manual-only** (`make iso-smoke-virtualbox`
/ `make iso-smoke-virtualbox-efi`). The 9.26.2 release evidence cites exactly
the CI set — "clean build and BIOS, UEFI, and 4K live-desktop smoke tests"
(`docs/9.26.2-ISSUE-STATUS.md:111-114`, run 34687879157), all QEMU. **Yes: the
VirtualBox run could have been skipped for 9.26.2 without failing anything —
no CI job, no `make release` dependency, and no release-preflight check would
have noticed.**

Two further gaps matter for this issue specifically:

- The script deliberately does **not** test the reporter's configuration. Lines
  108-109 state that Linux 7.1 rejects VirtualBox's VMSVGA `vmwgfx` device, so
  the test uses `VBoxSVGA`. A reporter accepting VirtualBox's default gets
  **VMSVGA**, an adapter the project's own harness routes around.
- The probe *requires* Compiz as the EWMH WM
  (`scripts/vm/live-desktop-probe.py:45-55`), so a desktop that boots with no
  window manager at all (see section 3) would fail the smoke test under
  VBoxSVGA — but that failure mode was never exercised under default VMSVGA.

## 2. Launch path: desktop file to Calamares, and what can freeze the session silently

Chain:

1. `overlays/etc/skel/Desktop/install-spaced-linux.desktop:7` —
   `Exec=/usr/local/bin/install-spaced-linux`, `Terminal=false` (line 9),
   `StartupNotify=true` (line 11). Only the installer launcher is seeded on
   the live desktop (`scripts/iso/01-configure.chroot:79-81` deletes every
   other desktop file; issue #191).
2. `overlays/usr/local/bin/install-spaced-linux` (71 lines):
   - Lines 5-8: `pgrep -f '^/usr/bin/calamares([[:space:]]|$)'` guard; exits 1
     with a stderr-only message if it thinks Calamares is already running.
   - Lines 14-43: `reset_stale_installer_mounts` — `findmnt` scan plus
     `sudo swapoff --all` and `sudo umount --recursive/--lazy` of
     `/tmp/calamares-root-*` trees.
   - Lines 46-49: `sudo mv /etc/fstab /etc/fstab.orig.calamares`, restored by
     the `trap cleanup` handler (lines 51-58).
   - Line 60: `xhost +si:localuser:root` so the root Calamares can connect to
     the live user's X server.
   - Lines 66-71: `sudo --preserve-env=DISPLAY,XAUTHORITY,DBUS_SESSION_BUS_ADDRESS
     env QT_AUTO_SCREEN_SCALE_FACTOR=1 QT_QUICK_BACKEND=software
     QSG_RHI_BACKEND=software LIBGL_ALWAYS_SOFTWARE=1 /usr/bin/calamares`.
     No `pkexec` anywhere — `scripts/check.sh:637-646` asserts the sudo form
     and forbids `pkexec calamares`, because pkexec cannot authorize reliably
     in the live MATE session.
3. The live sudo grant comes from `/etc/sudoers.d/spaced-live`
   (`scripts/iso/01-configure.chroot:58-59`, `user ALL=(ALL:ALL) NOPASSWD:
   ALL`), removed from installed systems by Calamares cleanup
   (`overlays/etc/calamares/modules/shellprocess@spaced-cleanup.conf:13`).
   The live session also runs `overlays/usr/local/bin/spaced-live-session`
   (screensaver/DPMS inhibit, autostarted per
   `overlays/etc/xdg/autostart/spaced-live-session.desktop`, removed on
   install per the same cleanup file, line 14).

Steps that can block the whole X session instead of failing visibly (ranked by
plausibility for "click does nothing"):

- **(a) Silent early exit, no terminal.** `Terminal=false` means every
  `exit 1` path (pgrep false positive, stale-mount release failure at line 43,
  fstab move failure) prints to nowhere the GUI user can see. `StartupNotify`
  may briefly show a spinner and then stop — perceived as "does nothing".
- **(b) `sudo` prompting.** If `/etc/sudoers.d/spaced-live` is absent or
  unreadable in that boot, each `sudo` blocks on a password prompt with no
  terminal to answer it. The launcher appears dead.
- **(c) `xhost` failure.** If line 60 fails (stale/absent authority), the root
  Calamares cannot connect to `:0` and dies with an X error, again invisible.
- **(d) `umount`/`swapoff` hanging on a wedged virtual DVD.** A lazy-recursive
  umount against a stuck VirtualBox SATA DVD device can block the script
  before Calamares ever starts.
- **(e) Calamares window never painting.** The launcher already forces the Qt
  software rendering path because "VirtualBox's emulated VMSVGA adapter can
  otherwise wedge the QML slideshow after the first page"
  (`install-spaced-linux:64-65`). If the software path is still insufficient
  on the reporter's adapter/driver, the process runs but no window appears —
  "does nothing" even though the launch technically succeeded.
- **(f) Session-wide input freeze (section 3).** If Compiz never started, no
  click on anything works; the installer is then a second victim, not the
  cause. This matches "the entire VM was locked up" better than (a)-(e), which
  explain only the installer.

The #192 "remove installation media" helper is **exonerated for the launch
failure**. `overlays/usr/local/bin/spaced-reboot-after-install` is a 14-line
`zenity --question` dialog wired solely as
`restartNowCommand` in `overlays/etc/calamares/modules/finished.conf:1-4`, i.e.
it runs only on Calamares' Finished page after a completed install, and is
deleted from installed systems
(`shellprocess@spaced-cleanup.conf:18`). It cannot run at launcher time. (Side
note, not this issue: if `zenity` were missing it exits 1 at line 13 and never
reboots; a Cancel answer also skips the `exec /sbin/reboot` on line 10.)

## 3. Graphics: VMSVGA without 3D, Compiz, and the "visible but frozen" mode

`overlays/usr/local/bin/spaced-window-manager` is MATE's required window
manager (`overlays/usr/share/glib-2.0/schemas/90_spaced-linux.gschema.override:25-26`).
Policy is explicit: **no fallback** — "if Compiz cannot start the desktop
session fails loudly rather than silently replacing it"
(`spaced-window-manager:1-5`; `docs/FIXES.md:25`).

`can_compiz` (lines 7-17) requires `$DISPLAY`, `glxinfo`, `direct rendering:
Yes`, and an `OpenGL renderer string` (with a 15 s timeout). Otherwise the
script logs and `exit 1` (lines 19-22) and the session runs **with no window
manager**: Caja can still paint the desktop and icons, the panel can render,
but nothing can take focus, move, or receive clicks normally — the screen
looks alive while all input is effectively dead. That is exactly the reported
"locked up, nothing was clickable or selectable" signature, and it is distinct
from a kernel panic or Xorg crash (screen would typically freeze or go black).

Under VirtualBox's default VMSVGA with 3D disabled there is no usable GLX
direct-rendering context for Compiz (llvmpipe indirect at best), so
`can_compiz` is expected to fail and the no-WM path is the predicted outcome.
The repository already knows VMSVGA is hostile: the installer forces software
Qt rendering because VMSVGA wedges the QML slideshow
(`install-spaced-linux:64-65`), and the smoke harness avoids VMSVGA entirely
(`smoke-iso.sh:108-109`). There is no llvmpipe/LLVMpipe special case and no
Marco/metacity fallback by design. A secondary "restart loop" mode exists
(lines 34-63: Compiz crash → restart with backoff), which would present as
flickering/choppy input rather than a hard freeze.

Caveat: without the reporter's `glxinfo`/`~/.xsession-errors`/`Xorg.0.log`
this remains the leading hypothesis, not a confirmed diagnosis — mouse-grab
(Guest Additions absent, pointer captured by the VM window) can mimic part of
the symptom. The discriminating question is whether the mouse pointer itself
moves (grab problem) versus moves-but-nothing-focuses (no-WM problem).

## 4. Network Servers icon: why live-VirtualBox shows it and the physical install does not

Facts:

- The icon is enabled by default image-wide:
  `90_spaced-linux.gschema.override:58-62` sets
  `org.mate.caja.desktop volumes-visible=true` and
  `network-icon-visible=true` (the latter kept so Gigolo/gvfs shares reappear,
  issue #184).
- It is a **virtual** Caja desktop link for `network:///`, not a file in
  `~/Desktop` — cf. `docs/troubleshooting/desktop-app-integrations.md:23-28`.
  Looking in the Desktop folder proves nothing about it.
- Issue #190 ("Network Servers icon visibility") shipped in 9.26.2 a neutral
  gray scalable fallback,
  `overlays/usr/share/icons/hicolor/scalable/places/network-server.svg`, so
  every shipped light/dark palette renders the place icon
  (`docs/9.26.2-ISSUE-STATUS.md:70`). Before 9.26.2, palettes lacking that
  icon showed a broken/missing glyph — easy to read as "no icon".
- Both live and installed images ship `gvfs-backends` and `gigolo`
  (`config/packages.yaml:4,28`), and the live image compiles the schemas at
  build time (`01-configure.chroot:32`).

Why the two systems differ — most likely first:

1. **The icon was always enabled; 9.26.2 just made it render.** The reporter
   compares a 9.26.2 live desktop (with the #190 fallback) against a physical
   install that may predate 9.26.2, retain an older icon cache, or use a
   palette that previously showed a broken glyph. This alone explains a "new"
   icon with no settings change.
2. **Live session reads stock defaults; installed users carry history.**
   The live user gets compiled-in override values. An installed user's dconf
   database may predate the override or contain an explicit
   `network-icon-visible=false`, which a schema default never overrides.
3. **Network availability differs.** The live session runs on VirtualBox NAT
   with networking up, so `gvfsd-network`/DNS-SD has something to browse; a
   physical install with a different network state (or stopped browsing stack)
   may show nothing behind the icon, and some users then hide it.
4. Least likely: a real live-vs-installed packaging difference — the cleanup
   module (`shellprocess@spaced-cleanup.conf`) removes installer entrypoints
   but never touches Caja settings, gvfs, or icons.

Cross-reference: issue #184 established that Gigolo shares are ordinary gvfs
mounts gated by `volumes-visible` plus stale per-monitor positions
(`docs/9.26.2-ISSUE-STATUS.md:72`,
`docs/troubleshooting/desktop-app-integrations.md:30-50`). The Network Servers
browse icon is the sibling gate under `network-icon-visible`. Neither is
evidence of a regression by itself.

## 5. Conclusion

### Ranked likely causes

1. **No window manager under default VMSVGA without 3D.** `can_compiz` fails
   (no direct GLX), `spaced-window-manager` exits 1 by design, MATE runs
   WM-less: screen painted, all input dead. Explains the *whole-VM* freeze;
   untested because the harness pins VBoxSVGA and CI never runs VirtualBox.
2. **Installer failing invisibly before Calamares paints** (`Terminal=false`
   + sudo/xhost/pgrep early exits, or the QML slideshow still wedged on
   VMSVGA despite the software-GL overrides). Explains "launcher does
   nothing" even if the session were otherwise alive.
3. **Calamares process alive but window never composited** (software-QML
   limits on the reporter's GPU/CPU/RAM allocation). Needs `ps` output to
   separate from (2).
4. **Pointer capture / Guest Additions confusion.** Possible contributor, but
   it does not explain zero response to keyboard/focus; lowest rank pending
   the "does the pointer move?" answer.
5. **The #192 zenity reboot helper.** Ruled out: Finished-page only.

The Network Servers icon is almost certainly the #190 fallback rendering a
long-enabled virtual icon on the fresh live session — cosmetic, not a
regression signal.

### Exact information to request from the reporter

- VirtualBox version, host OS, Guest Additions installed or not.
- VM settings: graphics controller (VMSVGA / VBoxSVGA / VBoxVGA), 3D
  acceleration on/off, video memory, RAM, CPUs, EFI or BIOS (and whether the
  EFI toggle changed anything).
- Does the mouse pointer itself move inside the VM window? Does the host key
  release capture? Does Ctrl+Alt+F2 (or Host+F2) reach a console?
- From a console or SSH: `ps aux | grep -i -E "calamares|pkexec|zenity|compiz"`.
- `~/.xsession-errors`, `/var/log/Xorg.0.log`, and
  `glxinfo -B | grep -i -E "direct rendering|renderer string"`.
- On both live and installed systems:
  `gsettings get org.mate.caja.desktop network-icon-visible`,
  `gsettings get org.mate.caja.desktop volumes-visible`, `gio mount -li`,
  and the icon theme in use.
- Whether the installer was tried more than once (the pgrep guard bites on
  retry if a first Calamares is wedged but alive).

### Reproduction recipe for the maintainer (defaults, not the harness config)

```bash
ISO=build/iso/spaced-linux-9.26.2-amd64.iso
VBoxManage createvm --name spaced-218-vmsvga --ostype Debian_64 --register
VBoxManage modifyvm spaced-218-vmsvga --memory 2048 --cpus 2 --vram 128 \
  --graphicscontroller vmsvga --accelerate-3d off --firmware bios \
  --boot1 dvd --nic1 nat
VBoxManage storagectl spaced-218-vmsvga --name SATA --add sata --controller IntelAhci
VBoxManage storageattach spaced-218-vmsvga --storagectl SATA --port 0 \
  --device 0 --type dvddrive --medium "$ISO"
# Interactive: observe desktop, move pointer, try clicks, launch installer.
VBoxManage startvm spaced-218-vmsvga --type gui
# Control case (what the current smoke test covers):
# repeat with --graphicscontroller vboxsvga and compare.
# Optional EFI variant: add --firmware efi to either case.
VBoxManage controlvm spaced-218-vmsvga screenshotpng /tmp/218-live.png
VBoxManage controlvm spaced-218-vmsvga poweroff
VBoxManage unregistervm spaced-218-vmsvga --delete
```

Headless variant: forward SSH (`--nat-pf1 "live-ssh,tcp,127.0.0.1,2223,,22"`)
and run `scripts/vm/live-desktop-probe.py` plus the launcher under
`timeout`, capturing `ps`, `~/.xsession-errors`, and `glxinfo -B`.

### Smallest proposed changes, per likely cause (described, not implemented)

1. **Cover the default adapter.** Add a VMSVGA/no-3D leg to the VirtualBox
   smoke matrix (or a `SPACED_VBOX_GRAPHICS` knob defaulting to both
   controllers across the two existing jobs) and assert the probe's
   Compiz/EWMH checks there. This is the only change that would have caught
   the leading hypothesis before release.
2. **Make launcher failures visible.** On any early exit, show the stderr
   text with `zenity --error` (zenity is already in the image,
   `config/packages.yaml:76`) or `xmessage` fallback before exiting, so
   "does nothing" becomes an actionable dialog. One guarded block at the top
   of `install-spaced-linux`; no behavior change on success.
3. **Decide the no-WM policy for VMs explicitly.** Either document that
   VirtualBox requires VBoxSVGA (or 3D on) in the install guide, or add a
   narrow, logged software-compositing allowance for the live session only —
   a deliberate exception to the `FIXES.md:25` no-fallback rule, not a silent
   global fallback.
4. **Installer-specific:** log launcher attempts to a fixed live-session file
   (e.g. append `date`, `pgrep` state, `xhost`/`sudo -n true` results) so the
   next such report arrives with evidence instead of "does nothing".
5. **Network Servers icon:** no code change proposed. If reports persist,
   document that the browse icon is default-on per
   `network-icon-visible=true` and how to hide it per-user; verify the
   installed-vs-live difference with the `gsettings`/`gio` outputs above
   before touching defaults.
