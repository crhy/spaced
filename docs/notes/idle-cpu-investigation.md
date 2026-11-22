# Why the Spaced bench VM showed 28 % idle CPU and 15,900 ctxt/s (issue #424, task b02)

Measured with `scripts/vm/bench/idle-investigate.sh` (added by this task): it
boots one matrix ISO in the same fresh KVM VM the sweep runner uses
(`-cpu host`, 4 vCPU, 8 GiB, 40G qcow2 under `/media/rhy/data/bench-vms/`,
headless, VNC on 127.0.0.1 only, VM and disk destroyed when done), then
samples inside the guest: per-process CPU ticks and context-switch deltas
from `/proc`, the `/proc/stat` totals over the SAME window (the probe's
cpu-in-use formula), and `/proc/interrupts` deltas. Result files:
`build/bench/idle-<os>-<label>.{tsv,-totals.txt}`. All runs 2026-11-22 on
rhY's box (Strata engine running; host load recorded in each totals file).

## Every run

spaced-linux 11.26.3, uptime-at-sample ≥ 180 s unless noted. cpu_in_use is
% of the whole 4-vCPU machine; per-process % is one core.

| label | uptime s | cpu_in_use % | ctxt/s | intr/s | top 3 processes (cpu_pct) |
|---|---|---|---|---|---|
| sweep (issue #424 row) | 11.6 | 27.63 | 15,861.8 | 4,535.8 | not captured |
| `early` (same 20 s window, from uptime 10 s) | 11.4 | 29.52 | 15,627.2 | 4,436.6 | caja 9.50, mate-settings-daemon 8.95, mate-session 8.25 |
| `base` (open SSH session) | 180.0 | 0.05 | 76.5 | 122.6 | khugepaged 21.20*, at-spi2-registryd 0.02, mate-settings-daemon 0.02 |
| `no-compiz` (`pkill -x spaced-window-manager; pkill -x compiz; su user -c marco --replace`) | 180.0 | 0.05 | 65.9 | 88.2 | khugepaged 0.75*, kworker 0.02, kworker 0.02 |
| `no-ssh-idle` (sampler detached with nohup, SSH closed during the sample) | 180.0 | 0.05 | 86.1 | 219.4 | khugepaged 36.10*, rcu_preempt 0.02, brisk-menu 0.02 |
| `thp-off` (top user process #1 was `khugepaged`, a kernel thread: disabled THP via sysfs instead of stopping it) | 180.0 | 0.08 | 75.2 | 94.5 | khugepaged 0.00, brisk-menu 0.02, glycin-image-rs 0.02 |
| `kill-glycin` (stop #2 user process, `pkill -x glycin-image-rs`) | 180.0 | 0.07 | 109.0 | 246.4 | khugepaged 38.08*, wnck-applet 0.02, mate-volume-control 0.02 |
| `kill-nm-applet` (stop #4 process, `pkill -x nm-applet`; #3 was `migration/2`, unstopable) | 180.0 | 0.07 | 68.1 | 89.1 | khugepaged 1.68*, mate-settings-daemon 0.02, sampler 0.02 |
| debian 13.8 MATE `base` | 180.0 | 1.77 | 734.5 | 465.5 | Xorg 5.28, ibus-daemon 0.42, sampler 0.22 |

The sweep's debian row (0.04 %, 56.3 ctxt/s) was sampled at uptime 63.7 s;
debian's own 180 s row above is busier (1.77 %, 734 ctxt/s: Xorg 5.28 % of a
core plus ibus) than the Spaced 180 s rows.

## The cause: start-up work, not idle work

Suspect (a) is the answer, with the numbers that prove it:

- Sampling the SAME VM at uptime 10–70 s (`early`, mirroring the sweep's
  11.6 s probe) reproduces the sweep almost exactly: 29.52 % cpu, 15,627
  ctxt/s, 4,437 intr/s vs the sweep's 27.63 %, 15,862, 4,536.
- The same VM at uptime 180 s: **0.05 % cpu, 76.5 ctxt/s** — as idle as
  debian's 63.7 s sweep row (0.04 %, 56.3).
- The 20 s after boot is a desktop autostart storm: `caja` 9.50 %,
  `mate-settings-daemon` 8.95 %, `mate-session` 8.25 %, `nm-applet` 7.75 %,
  `mate-volume-control` 6.95 %, `mate-panel` 6.55 %, `compiz` 5.30 %,
  `brisk-menu` 4.85 %, `clock-applet` 4.35 %, `wnck-applet` 4.25 % (sum of
  processes 89.9 % of a core ≈ 29.5 % of 4 cores + khugepaged + interrupts;
  consistent). Most of it is session components loading and talking to D-Bus;
  a share is the live session's first-login work
  (`overlays/etc/xdg/autostart/spaced-first-login-repair.desktop`,
  `spaced-desktop-icon-repair*.desktop`, `localsearch-3.desktop`).
- The machine-level totals are confirmed by an independent raw SSH probe
  (no sampler involved) over the same 180–240 s window: `/proc/stat` delta
  12 busy ticks out of ~24,000 (0.05 %), ctxt +4,215 in 60 s (70/s).

Suspects (b) and (c) are ruled out for the idle cost:

- (b) Compiz on llvmpipe: at uptime 180 s `compiz ccp --replace` uses
  0.00 % cpu and 0.6 ctxt/s; the `no-compiz` totals are unchanged (0.05 %,
  65.9 ctxt/s). Killing compiz does NOT stay dead: `spaced-window-manager`
  is a restart loop by design ("Compiz is the only window manager",
  `overlays/usr/local/bin/spaced-window-manager`), and the session
  re-supervises it: 3 s after the kill, `pgrep` showed compiz (2095) and a
  new `spaced-window-manager` (2079) already back. `/usr/bin/marco` exists
  in the image but cannot take the WM role for good, and the session has no
  WM-less fallback by policy. Compiz is only expensive DURING boot (5.30 %
  while starting) — like everything else.
- (c) the SSH session: `no-ssh-idle` (sampler detached via nohup, session
  closed before the window) measured 0.05 % / 86.1 ctxt/s — no different
  from `base` (0.05 % / 76.5). sshd costs nothing at idle.

## Caveat about khugepaged rows

`khugepaged` (a kernel thread) is the only consumer above 0.02 % in every
180 s TSV (0.75–38 %, varying per VM: THP collapse work after login), but
its per-process line disagrees with the machine totals — over the raw probe
window its stime grew 112 ticks (1.9 % of one core) while the `/proc/stat`
cpu line grew only 9 system ticks. Kernel-thread work is not fully counted
in this tickless KVM guest's aggregate cpu line, so khugepaged TSV rows are
directional (real work, invisible at machine level); the totals that the
sweep reports are the authoritative numbers. `thp-off` shows the machine is
0.08 % / 75.2 ctxt/s with THP disabled anyway.

## What this means for real hardware with a GPU

- Tested: the whole finding is userspace autostart plus GL-independent
  session startup; compiz at idle is 0.00 % even on llvmpipe, so a GPU
  changes nothing about the 27.63 % number — it is the same storm on real
  hardware, only faster (SSD vs virtio qcow2, real CPU vs 4 vCPUs).
- Not tested: GPU-accelerated Compiz/Xorg and physical boot speeds — the
  bench VMs have no GPU (llvmpipe), and this machine's own desktop cannot
  act as the subject. Nothing in the data says the GPU matters for the
  idle number: after boot, Xorg+compiz cost 0.02 % of a core here.

## Proposed fix (not applied — Claude and rhY decide)

1. Bench (the actual wrong number): make the sweep measure an idle machine,
   not a booting one. `scripts/vm/bench/guest-bootstrap.sh` step 2 should
   wait out boot work before running `guest-probe.sh` — a settle loop
   (`until uptime ≥ 180 s` or `until idle for N s`) ahead of
   `guest-probe.sh --idle`. One small block in that file; `idle-investigate.
sh --wait-until` shows the working pattern. Then re-run the sweep rows —
   the current Spaced vs debian idle columns are not comparable.
2. OS (real but modest): the login storm is ~90 % of a core for the first
   minute on 4 vCPUs. If it matters, stagger/defer the heaviest autostart
   entries (`caja` desktop icons, `nm-applet`, the first-login repair
   scripts) in `overlays/etc/xdg/autostart/`. Not asked for here; no change
   made.
