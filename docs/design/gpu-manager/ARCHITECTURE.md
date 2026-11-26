# ARCHITECTURE.md — how Spaced GPU Manager is applied safely (11.26.4)

Design only. The safety backend is the working candidate on branch
`gpu-manager/11.26.4` and is **kept as-is**: journaled Xorg changes, the boot guard, the
confirmation deadline, rollback, refusal of custom Xorg, PCI addresses as identities,
UUID-based CUDA selection. This document adds the role plumbing, the display-check and
boot-count fallback the review asked for, and the 11.26.4 test plan.

No systemd anywhere (spaced-no-systemd). Services are sysvinit (`/etc/init.d`,
`update-rc.d`, `service`), the display manager is LightDM.

## 1. Components

| File (installed) | Privilege | Job |
|---|---|---|
| `usr/lib/spaced-linux/spaced_gpu.py` | user | discovery (PCI ids as identity, VRAM, connectors from `/sys/class/drm`, link capability), role state, `xorg_config()`, journal + `Trial` state machine, `offload_environment()`, `compute_environment()`, driver lock |
| `usr/lib/spaced-linux/spaced-gpu-manager.py` | user | the UI (Overview / Roles / Move monitor / Drivers). `--preview` = read-only mode for source trees |
| `usr/lib/spaced-linux/spaced-gpu-helper` | root via polkit | fixed verbs only: `stage <pci>` · `confirm` · `revert` · `watchdog`. Never a path, never a shell string |
| `etc/init.d/spaced-gpu-guard` | root at boot | starts the watchdog before LightDM (`X-Start-Before: lightdm`), `stop` deliberately does not disarm a running trial |
| `etc/xdg/autostart/spaced-gpu-trial.desktop` | user | reopens the countdown window in the new session (`--confirm-trial`, exits when no trial) |
| `usr/share/polkit-1/actions/com.spacedlinux.gpu.policy` | — | one action `com.spacedlinux.gpu.configure`, `allow_active=auth_admin`, exec-path pinned to the helper |
| `usr/bin/spaced-gpu-launch` (new, user) | user | the per-launcher role plumbing (below); no root |
| `etc/X11/xorg.conf.d/90-spaced-gpu-manager.conf` | root | the only file this app writes; numbered last so it wins |

## 2. Roles → what actually changes

A role is a *recorded intent*; only **Desktop** changes the system. Nothing else needs
root, so nothing else needs a rollback.

| Role | Applied as |
|---|---|
| **Desktop** | `xorg.conf.d` snippet written by the helper through the journal (below) + reboot + LightDM restart |
| **Games** | per-launcher environment, written to `~/.local/share/spaced-linux/gpu-roles.json`; `spaced-gpu-launch` / the game's own launcher wrapper exports `__NV_PRIME_RENDER_OFFLOAD=1 __GLX_VENDOR_LIBRARY_NAME=nvidia __VK_LAYER_NV_optimus=NVIDIA_only` (single NVIDIA card) or `DRI_PRIME=pci-<address>` (Mesa). Never a global environment, never a session-wide export |
| **AI & compute** | same file; the launcher exports `CUDA_VISIBLE_DEVICES=<GPU-uuid>` so CUDA device 0 is *this* card even if enumeration order changes (NVIDIA's documented UUID form). AMD/Intel compute is refused with a message, not guessed indices |
| **Off** | a mark in the same file: the launcher refuses to start there and says why. No power changes — `power-off` is not implemented and never advertised (DESIGN.md §9) |

Multiple proprietary NVIDIA cards: automatic Games selection is **refused** until the
PCI→RandR-provider mapping is verified on real hardware; the app tells the user to pick
the card inside the game. No invented enumeration indices.

## 3. Desktop change = journalled transaction

`spaced_gpu.py` `Trial` (unchanged from the candidate) is the whole safety story:

1. **Lock**: shared `flock` with the NVIDIA driver transaction. A pending driver reboot
   blocks a desktop trial and vice versa (`driver_reboot_pending`, incl. legacy empty
   markers by mtime).
2. **Preconditions**: a connector with `status=connected` on the target card; a working
   desktop driver (`amdgpu/radeon/i915/xe/nvidia`); no unconfirmed previous trial; the
   guard registered in `/etc/rc2.d`; a live-boot marker check.
3. **Refuse hand-made config**: if any `xorg.conf`, `/etc/X11/xorg.conf.d/*.conf` or
   `/usr/share/X11/xorg.conf.d/*.conf` (other than the managed file) contains a
   `Device`/`Screen`/`ServerLayout` section, or the managed path is a symlink, or the
   managed file differs from what the journal wrote → refuse and ask for manual review.
   Admin edits are never overwritten.
4. **Journal before touching**: `previous` + `candidate` are written to
   `/var/lib/spaced-gpu-manager/trial.json` (atomic write + `fsync` + directory
   `fsync`) **before** the Xorg file changes, so a power cut mid-write is recoverable.
5. **Snippet** (validated, PCI address split from a regex, decimal `BusID`):
   ```
   Section "Device"  Identifier "SpacedDesktopGPU"  Driver "amdgpu|nvidia|…"
       BusID "PCI:<dec>@<domain>:<bus>:<slot>.<func>"
   Section "Screen" …  Section "ServerLayout" … Option "AllowNVIDIAGPUScreens" "true"
   ```
6. **Reboot**, then the trial begins on the *next* boot only (`staged_boot` ≠
   `trial_boot`), never in the boot that staged it.

## 4. Automatic rollback when X does not come up

Three layers, all sysvinit/LightDM, none of them dependent on the desktop working:

**Layer 1 — the confirmation deadline (candidate, kept).** The guard runs before
LightDM (`X-Start-Before: lightdm`) and calls `begin_boot()`: a staged trial becomes a
trial with `deadline_boot_seconds = CLOCK_BOOTTIME + 180`. `CLOCK_BOOTTIME` counts
suspend and ignores clock changes; restarting the guard cannot extend a deadline
(the deadline lives in the journal); an expired confirmation is refused. On expiry the
watchdog re-takes the lock, calls `revert()` (restores `previous` or deletes the file)
and runs `service lightdm restart` — the previous desktop is back without a reboot.
The countdown window (autostart) is the user's only action; "Keep this desktop" calls
`confirm`, which re-checks the boot id, the deadline and that the file still matches
the journal.

**Layer 2 — LightDM display-setup check (new).** LightDM's display-setup hook
(`/etc/lightdm/display-setup-script`, registered by this package) runs once per
LightDM session start. It asks `spaced_gpu.py` for the managed card's connector state
and writes one marker:
`/var/lib/spaced-gpu-manager/display-ok` (contents: boot id + the trial's PCI) when a
screen is actually driving output on the card the journal expects. If the trial reaches
its deadline without that marker, Layer 1 rolls back even though nothing was confirmed —
so "X never came up" and "X came up on the wrong card" both roll back automatically.
The check is a read of `/sys/class/drm/*` and LightDM's own log; it starts nothing.

**Layer 3 — boot-count fallback (new).** `spaced-gpu-guard` keeps
`/var/lib/spaced-gpu-manager/boot-count`. A staged trial increments it; the guard, on
`start`, rolls the trial back and restarts LightDM if the same staged trial has now
booted **twice** without a confirmation, i.e. the machine rebooted into a layout that
never reached a confirmable session (a crash-loop or a hung display before any
login). The counter is journalled with the trial so a `revert` clears it. The guard
never reboots, never touches a machine that is not in a trial, and never repairs a
kernel hang or a failed boot (that stays honest in the docs, as the candidate says).

**Text-console recovery command** (documented, in the app's own strings):

```
sudo /usr/lib/spaced-linux/spaced-gpu-helper revert
sudo reboot
```

`revert` refuses to replace an admin symlink or a file that changed outside the app, and
restores `previous` (or removes the managed file) — the same code path the watchdog uses.

## 5. Privilege model

- UI is unprivileged and refuses to mutate in `--preview`; the buttons are insensitive,
  not just hidden.
- Every mutation goes through `pkexec` → the helper → the polkit action
  (`auth_admin` for active sessions). The helper accepts **exactly four verbs**, a
  lowercase normalised PCI address (`normalize_pci` regex, injection refused), and
  nothing else: no paths, no shell, no environment, fixed `PATH`, `LC_ALL=C`,
  `syslog` for failures, `-I` interpreter flag.
- All state writes are atomic + fsynced; a corrupt journal is fail-closed (no
  confirmation, no automatic action beyond revert).

## 6. Test plan for 11.26.4

Unit / host (already passing on the candidate, kept green — `python3 -m unittest
discover -s tests`): 41 GPU Manager tests covering PCI normalisation, offload refusal,
Xorg preservation, journaling, reboot interlocks, confirmation, rollback, watchdog
deadlines, UUID compute selection; the GTK/Xvfb smoke test (3 cards, copy dialogs,
countdown, 880×680 preview); the CUDA probe (driver enumeration, no contexts).

New for 11.26.4, in order of the risk they cover:

1. **VM with a deliberately broken layout proves rollback.** KVM VM (no GPU passthrough)
   with the managed file pointed at a device that cannot drive X (`Driver "modesetting"`
   + a BusID that does not exist). Gate: boot staged → LightDM starts and fails or the
   display check never writes `display-ok` → within the deadline the watchdog reverts,
   restarts LightDM and the old session returns; confirm no reboot was needed and the
   journal reads `phase: reverted`. Then the inverse: a good layout, confirmed inside the
   deadline → survives the next boot.
2. **Layer-2 hook test**: force the display check to see no connector on the expected
   card (fake `/sys` root, as the unit tests already do) → rollback fires without the
   deadline elapsing.
3. **Boot-count fallback test**: staged trial, reboot twice with no confirmation →
   second boot reverts and logs the reason; a confirmed trial leaves the counter alone.
4. **Driver-transaction interlock test**: pending NVIDIA reboot marker + attempted
   desktop trial → refused; pending trial + attempted `--install` → refused.
5. **bigboy physical test with rhY moving the cable** (the only test that proves the
   guided move): record before/after desktop VRAM on the 4070 (~310 MiB today), move the
   1080p monitor from the 4070's HDMI to the motherboard's HDMI, follow the Move-monitor
   page, confirm inside 3 minutes. Record: measured VRAM change, game FPS delta, whether
   G-Sync/VRR disappears, board-port resolution/refresh limits. Nothing in the UI may
   promise a saving that this test did not measure.
6. **Escape-hatch rehearsal**: on bigboy, deliberately let the trial expire → the old
   desktop returns; then `sudo … revert` from a text console → reboot → previous layout.

## 7. Ship checklist for 11.26.4

- Candidate branch merged to `main` (never a PR: spaced-no-prs rule), issue #426 closed
  only after merge (AGENTS.md).
- `docs/GPU-MANAGER.md` rewritten to the approved wording (this design), including the
  plain-word table from DESIGN.md §3; `docs/notes/` note added for the 11.26.4 decision.
- Release notes: "GPU roles ship in 11.26.4" (rhY 2026-11-21), not 11.26.3.
- All of TODAY.md §1–7 still works; the UI test names the old commands as compatibility
  entry points.

## 8. Open items after approval

- Games role: verify PCI→RandR-provider mapping on a real multi-NVIDIA box before
  offering automatic selection.
- Flatpak/container access per role: `spaced-bazaar` override UI, not a global env.
- AMD/Intel compute: name the tools inside the app rather than refusing generically.
- A `spaced-gpu-launch` desktop entry per launcher (Steam/Lutris/Wine) so the "Games"
  role is one click, if rhY wants it in 11.26.4.
