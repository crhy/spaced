# Xlibre as an opt-in test image (issue #314)

Status: **open**. Xorg is still the default display server of Spaced Linux, and
this page describes the reviewed way to try Xlibre without touching that default.
The 11.26.1 review of issue #314 sets the rule this page implements: moving the
display server needs ABI and packaging compatibility checks across Compiz/MATE,
Mesa, NVIDIA/AMD/Intel drivers, VirtualBox/QEMU, multi-monitor/hotplug,
suspend/reboot and an Xorg fallback/rollback path, so Xlibre is **first built as
an opt-in test image with a published hardware matrix**, and a default switch
waits until that gate is green.

## What is opt-in, and what is not

| File | Read by | Effect |
| --- | --- | --- |
| `config/packages.yaml` | `scripts/iso/package-list.sh` | the package set of every normal image; the `graphics:` group at lines 58-71 installs the Xorg server drivers |
| `config/xlibre-test-image.yaml` | `scripts/iso/xlibre-package-list.sh` only | the reviewed Xlibre set for a **test image**; `scripts/iso/package-list.sh` never reads it, so the default image cannot change |

`scripts/iso/xlibre-package-list.sh` refuses to print anything while any entry
still says `version: UNRELEASED` or lacks a 64-hex `sha256`, and it names every
unpinned entry in its message. That refusal is part of the gate:

```
! bash scripts/iso/xlibre-package-list.sh   # must keep succeeding while the set is unpinned
```

`tests/test_xlibre_optin_image.py` proves the default list still carries every
`xserver-xorg-*` entry and no Xlibre package, that the committed opt-in set
refuses, and that a fully pinned fixture emits the reviewed set, drops the
`xserver-xorg-*` entries it replaces and keeps the rollback entry.

The Xlibre set starts LightDM, the display manager already installed from
`config/packages.yaml:16`; nothing here adds an init service, and Spaced Linux
stays sysvinit-only.

## Building the opt-in image

1. **Pin every entry.** Replace each `version` and `sha256` in
   `config/xlibre-test-image.yaml` with the values published by XLibre, verified
   against the upstream package index at `https://deb.xlibre.org` (project site
   `xlibre.org`). Confirm the package names too: they are the names this task
   reviewed, not values this machine could check. Do the same job
   `config/external-artifacts.conf` requires for independently released
   components.
2. **Add the Xlibre repository to the test build only.** The Xlibre package set
   is not in the Devuan repositories, so a test build needs its own APT source
   and signing key staged under `build/` (or an environment override). Keep
   `config/iso.yaml` on Devuan `/merged`: `scripts/check.sh` rejects foreign
   Debian repository URLs, and no Xlibre source may reach a normal image.
3. **Compose the test image package list** in place of the normal one:

   ```bash
   set -euo pipefail
   xlibre_set=$(scripts/iso/xlibre-package-list.sh)   # fails here while anything is unpinned
   {
       scripts/iso/package-list.sh | grep -vE '^xserver-xorg-(video|input)-'
       printf '%s\n' "$xlibre_set"
   } | sort -u > build/live-build/config/package-lists/spaced.list.chroot
   ```

   The `grep -vE` filter removes exactly the packages named under `replaces:`
   in `config/xlibre-test-image.yaml` (`xserver-xorg-video-*` and
   `xserver-xorg-input-libinput`). `mesa-utils`, `libgl1-mesa-dri` and
   `mesa-vulkan-drivers` stay: they are not X server packages. The script's own
   output keeps the `fallback_boot: xorg` rollback entry.
4. **Build it as a test ISO.** Run the usual `make prepare` / `make lb-build`
   path against that list, name the result as a test image, and do not publish
   it as a release: `scripts/check.sh` enforces that `VERSION`, `config/iso.yaml`,
   os-release, the Calamares branding and the GRUB entries all agree, so this
   task does not bump the version and a test image must not pretend to be one.

## Hardware matrix to fill

Every row of the `matrix:` block in `config/xlibre-test-image.yaml` is
`result: pending`, and nothing in that file may be claimed as verified. Fill one
row at a time on the machine that can actually measure it, then record the
result there and the evidence in the issue.

| Row | What to measure | How |
| --- | --- | --- |
| `compiz-mate` | Compiz starts as the window manager, MATE panel, Brisk menu, Caja and the greeter come up on the Xlibre server, no crash on login or logout | boot the test image, then the desktop checks in `scripts/vm/qemu/live-checks.sh` and `docs/COMPIZ.md` |
| `mesa` | GLX works through Mesa: `glxinfo` reports the expected renderer, and a GLX client (`glxgls`, `eom`/Mesa demo) draws | `glxinfo`, `glxgls -info`, plus `libgl1-mesa-dri`/`mesa-vulkan-drivers` still resolving in the test set |
| `nvidia` | the NVIDIA driver works with the Xlibre server on real NVIDIA hardware, including the Spaced driver manager paths | `docs/NVIDIA-RECOVERY.md` and `overlays/usr/lib/spaced-linux/spaced-nvidia-helper` on a machine with the GPU |
| `amd` | the amdgpu stack (TearFree, secondary Radeon) drives the Xlibre server without the issue #298 crash | `scripts/tests/xorg-amdgpu-headless-test.sh` against the Xlibre server, plus a real AMD display |
| `intel` | integrated Intel graphics boots and draws (the `xserver-xorg-video-intel` row this set replaces) | real Intel machine, or the `graphics:` group's Intel path in `docs/10.26.3-TEST-PLAN.md` |
| `virtualbox` | the test image boots and the desktop starts in VirtualBox BIOS and EFI mode | `make vbox-smoke`, and `make vbox-smoke-default` for VirtualBox's own defaults, where exit 3 means Compiz cannot start (issue #218) |
| `qemu` | the test image boots and the desktop starts headlessly in KVM/QEMU, BIOS and EFI | `make iso-smoke-kvm iso-smoke-kvm-efi`, `scripts/vm/qemu/start.sh` |
| `multi-monitor-hotplug` | monitor layout follows plug/unplug, Brisk menu and icon positions repair, screensaver wake is correct | `overlays/usr/local/bin/spaced-display-repair` paths in `docs/DISPLAY-REGRESSIONS.md` |
| `suspend-reboot` | suspend, reboot and shutdown work from the desktop, no boot loop, no lost session | `scripts/vm/qemu/reboot-loop.sh`, `overlays/usr/local/bin/spaced-reboot-after-install`, MATE shutdown on real hardware |

A row counts as green only with a machine, the test image, and the command above
recorded against it. The default switch stays closed until every row is green.

## Xorg fallback and rollback

`fallback_boot: xorg` is not optional: `scripts/iso/xlibre-package-list.sh`
refuses a file that changes it, and the emitted set keeps
`fallback_packages: xserver-xorg-core`, the Spaced-rebuilt Xorg server staged by
`scripts/iso/stage-xorg-server.sh`. That keeps the Xorg boot entry alive on a
test system, which is what issue #314 asked for ("you might keep Xorg as a boot
option").

Rolling back on a machine where Xlibre fails:

1. Boot the Xorg entry; the Xorg server package is still installed.
2. Reinstall the Xorg driver packages the test image removed
   (`xserver-xorg-video-amdgpu`, `-ati`, `-radeon`, `-nouveau`, `-fbdev`,
   `-vesa`, `-intel`, `-all` and `xserver-xorg-input-libinput`) from the Devuan
   repositories.
3. Leave the APT pin and the transaction guard alone.
   `overlays/etc/apt/preferences.d/spaced-xorg-abi` and
   `overlays/usr/lib/spaced-linux/spaced-update-apt-guard` still refuse
   `xserver-xorg-core 2:21.1.25-1devuan1`, the X server that crashes the amdgpu
   driver (issue #298). The opt-in path never reads or edits them, and
   `tests/test_xlibre_optin_image.py` fails if they change or if the broken
   version appears in the opt-in file.

## Blockers, stated plainly

1. **Nothing is pinned, because upstream is unreachable from this build host.**
   `curl -L` returns `000` (no HTTP status) for both `https://deb.xlibre.org` and
   `https://xlibre.org`, while `https://github.com` and
   `http://mirror.hootsoftware.com` return 200, and `apt-cache policy` offers no
   Xlibre candidate in the configured sources. No version and no SHA-256 can be
   verified here, so the committed set ships with both fields explicitly
   `UNRELEASED` and the script refuses it.
2. **The driver and hardware rows need real machines.** This machine has
   `qemu-system-x86_64` and `qemu-img` in `/usr/bin`, but no GPU or driver
   hardware and no ISO or qcow2 of another OS, so the `nvidia`, `amd`, `intel`
   and `virtualbox` rows cannot be measured here, and `qemu` cannot be measured
   against a test ISO that cannot be built while the set is unpinned.

## Gate

```
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests \
    && bash scripts/check.sh \
    && ! bash scripts/iso/xlibre-package-list.sh
```

The last clause passes only while the refusal guard holds, which is exactly the
state this task leaves the repository in.
