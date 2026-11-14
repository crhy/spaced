# Spaced Linux 11.26 → 11.26.1 — measured efficiency and speed

Measured on 2026-11-14 with `scripts/vm/qemu/release-measure.sh` (added by this
measurement; it only reads the guest). Nothing in the product was changed to
produce these numbers.

## Method

* One live ISO booted cold per measurement: `-cdrom <ISO> -boot order=d`, **no
  disk**, so every boot starts from scratch.
* Identical VM for both ISOs: `qemu-system-x86_64 -enable-kvm -cpu host -m 4096
  -smp 4 -device qemu-xhci,id=xhci -device usb-kbd,bus=xhci.0 -device
  usb-tablet,bus=xhci.0 -nic user,model=virtio-net-pci,hostfwd=tcp:127.0.0.1:2234-:22
  -rtc base=utc -vga std -global VGA.vgamem_mb=64 -display none -vnc
  127.0.0.1:45 -cdrom <ISO> -boot order=d`.
* Host: AMD Ryzen 7 7800X3D (8C/16T), 96 GiB RAM, kernel
  7.3.4+deb14-amd64, QEMU 11.1.3, KVM. Host load average is recorded in every
  run (`host_load_at_start`); the runs were interleaved old/new/old/new/... so
  host drift cannot favour one release. One VM at a time.
* 3 cold boots per ISO (6 boots total), plus 2 extra diagnostic boots per ISO
  for the `dpkg --audit` deep dive and the idle-CPU breakdown.
* "Desktop ready" = `mate-panel`, `caja` and `compiz` all running, polled every
  second over SSH; the host clock gives QEMU-start → ready, and the guest's
  `/proc/uptime` at the same instant gives the boot time without
  `systemd-analyze` (there is none: sysvinit).
* Idle window: 60 s with no commands sent to the guest; both `/proc/stat` and
  `/proc/interrupts` snapshots are taken inside the guest with the guest clock.
  `free -m`, `ps` and `dpkg-query` are read after the window.
* Wake-ups: `powertop`, `strace`, `perf` and `sysstat` are not in the ISO
  (`config/packages.yaml`), so the fallback the task allows is used:
  `/proc/stat` `ctxt` and `intr` deltas for the whole system, and
  `nr_switches` from `/proc/<pid>/sched` summed over the whole
  `spaced-display-repair --watch` process tree for the helper.
* Raw per-boot artifacts: `build/vm-tests/r02/<iso>/run-<n>/` (idle-window.txt,
  diskstats-*.txt, top10-rss.txt, apt-dpkg-timing.txt,
  display-repair-window.txt, qemu.log).

## ISOs (both verified before measuring)

```
$ cd build/iso && sha256sum -c spaced-linux-11.26-amd64.iso.sha256 spaced-linux-11.26.1-amd64.iso.sha256
spaced-linux-11.26-amd64.iso: OK
spaced-linux-11.26.1-amd64.iso: OK
```

| ISO | sha256 | size |
|---|---|---|
| 11.26 | `d3a9b7a536cd4075c48771f9bb00d9352ba70bfe6e3eb8e55a426cc6a0c9a05a` | 1634871296 B (1559.1 MiB) |
| 11.26.1 | `937030fcb2103d5115ddda6d2e9ade497d239b1ff250352ee01bb34a734b1d6f` | 1633140736 B (1557.5 MiB) |

Guest kernels: 11.26 `7.2.15+deb14-amd64`, 11.26.1 `7.3.4+deb14-amd64`.
dpkg: 11.26 `1.23.11`, 11.26.1 `1.23.12`.

## Raw numbers, per boot

| metric | 11.26 run 1 | 11.26 run 2 | 11.26 run 3 | 11.26.1 run 1 | 11.26.1 run 2 | 11.26.1 run 3 |
|---|---|---|---|---|---|---|
| host load at start (1 min) | 3.64 | 4.90 | 5.91 | 1.10 | 2.50 | 0.60 |
| SSH ready (s from QEMU start) | 26.5 | 26.4 | 26.4 | 26.4 | 30.5 | 26.4 |
| desktop ready (s from QEMU start) | 32.8 | 30.7 | 30.7 | 31.7 | 36.9 | 31.7 |
| `/proc/uptime` at desktop ready (s) | 16.27 | 14.14 | 14.15 | 15.20 | 18.03 | 15.18 |
| used memory after 60 s idle (MiB) | 1081 | 1074 | 1087 | 1068 | 1072 | 1088 |
| available memory (MiB) | 2835 | 2842 | 2829 | 2847 | 2844 | 2828 |
| process count | 192 | 191 | 193 | 196 | 194 | 195 |
| total RSS of top 10 (KiB) | 941160 | 939544 | 939772 | 942764 | 942920 | 942024 |
| installed packages | 1188 | 1188 | 1188 | 1200 | 1200 | 1200 |
| context switches/s idle | 4998.8 | 4843.4 | 4886.5 | 4782.3 | 4594.7 | 4440.2 |
| interrupts/s idle | 1327.1 | 1324.5 | 1341.3 | 1278.8 | 1195.3 | 1251.1 |
| idle CPU % (of 4 CPUs, 60 s) | 8.96 | 7.50 | 7.66 | 7.24 | 8.07 | 5.98 |
| boot disk reads, sr0 (MiB) | 252.9 | 256.0 | 256.0 | 255.8 | 258.3 | 261.6 |
| boot disk reads, loop0/squashfs (MiB) | 371.7 | 384.3 | 381.3 | 380.7 | 417.7 | 427.6 |
| `apt-get check` first (ms) | 128 | 118 | 116 | 274 | 121 | 120 |
| `apt-get check` second (ms) | 9 | 9 | 9 | 11 | 9 | 9 |
| `dpkg --audit` first (ms) | 75 | 79 | 72 | 6931 | 6865 | 6775 |
| `dpkg --audit` second (ms) | 10 | 10 | 10 | 81 | 63 | 84 |
| `spaced-display-repair` wake-ups, 120 s idle (`nr_switches` delta) | 27 | 27 | 27 | 0 | 0 | 0 |
| its reconcile `sleep` children seen in 120 s (lower bound) | 2 | 2 | 2 | 1 | 1 | 1 |

## Comparison (median of 3; "same" when the 3-run ranges overlap)

| metric | 11.26 median | 11.26.1 median | change % | better/worse/same |
|---|---|---|---|---|
| QEMU start → desktop ready (s) | 30.7 | 31.7 | +3.3 | same (30.7–32.8 vs 31.7–36.9) |
| boot time, `/proc/uptime` at desktop ready (s) | 14.15 | 15.20 | +7.4 | same (14.14–16.27 vs 15.18–18.03) |
| live SSH ready (s) | 26.4 | 26.4 | 0.0 | same (26.4–26.5 vs 26.4–30.5) |
| used memory after 60 s idle (MiB) | 1081 | 1072 | −0.8 | same (1074–1087 vs 1068–1088) |
| available memory (MiB) | 2835 | 2844 | +0.3 | same |
| process count | 192 | 195 | +1.6 | worse (191–193 vs 194–196, no overlap; +3 processes) |
| total RSS of top 10 (KiB) | 939772 | 942764 | +0.3 | worse (no overlap; +3 MiB, negligible) |
| context switches/s while idle | 4886.5 | 4594.7 | −6.0 | better (4843–4999 vs 4440–4782, no overlap) |
| interrupts/s while idle | 1327.1 | 1251.1 | −5.7 | better (1325–1341 vs 1195–1279, no overlap) |
| idle CPU % (60 s, 4 CPUs) | 7.66 | 7.24 | −5.5 | same (7.50–8.96 vs 5.98–8.07) |
| boot reads from the CD (sr0, MiB) | 256.0 | 258.3 | +0.9 | same |
| boot reads through squashfs (loop0, MiB) | 381.3 | 417.7 | +9.5 | same (371.7–384.3 vs 380.7–427.6, overlap) |
| ISO size (bytes) | 1634871296 | 1633140736 | −0.11 | better (1.7 MB smaller) |
| installed package count | 1188 | 1200 | +1.0 | worse (+12 packages: the live rescue group and the pinned components) |
| `apt-get check` (first, ms) | 118 | 121 | +2.5 | same (116–128 vs 120–274) |
| `apt-get check` (warm, ms) | 9 | 9 | 0.0 | same |
| `dpkg --audit` (first, ms) | 75 | 6865 | +9053 | **worse** (72–79 vs 6775–6931, no overlap) |
| `dpkg --audit` (warm, ms) | 10 | 81 | +710 | worse (10–10 vs 63–84) |
| `spaced-display-repair` wake-ups / 120 s idle | 27 | 0 | −100 | **better** (27–27 vs 0–0, no overlap) |

## What got better, and why

`spaced-display-repair --watch` reconciled the DPMS state every 30 s in 11.26
(`while sleep 30`) and every 300 s in 11.26.1
(`overlays/usr/local/bin/spaced-display-repair:234` `while sleep 300; do`,
commit `0f9e955`). Measured over 120 s of idle desktop: 27 scheduling events in
the helper's process tree in every 11.26 boot, 0 in every 11.26.1 boot. The
same direction shows up system-wide: −6.0 % context switches/s and −5.7 %
interrupts/s while idle, with the ranges of the two releases not overlapping.
Boot time, memory and idle CPU did not change measurably.

## `dpkg --audit` deep dive (2 extra boots per ISO)

The 90× first-run difference is reproducible (6775–6931 ms vs 72–79 ms) and is
not caused by our code. Probes inside the live session:

| probe | 11.26 (dpkg 1.23.11) | 11.26.1 (dpkg 1.23.12) |
|---|---|---|
| `dpkg --audit`, first run in the session | 3210 ms | 7355 ms |
| second / third run | 11 ms / 9 ms | 173 ms / 177 ms |
| after `echo 3 > /proc/sys/vm/drop_caches` | 2852, 1117, 236 ms | 8420, 8442, 8452 ms |
| what one cold audit reads (`/proc/<pid>/io`) | rchar 6644 B, read_bytes 1.94 MB, **syscr 11** | rchar 15185157 B, read_bytes **166 MB**, **syscr 1216** |
| dpkg's own CPU during a cold audit | 12-23 jiffies (0.12-0.23 s) | 765-864 jiffies (7.7-8.6 s) |
| `dpkg --admindir=/tmp/dpkgadm --audit` (same data on tmpfs) | 10 ms | 59 ms |
| `cat /var/lib/dpkg/status` cold | 74 ms | 43 ms |
| `/var/lib/dpkg/info` | 45979898 B, 4887 files | 46 MB, 4940 files |

Reading: dpkg 1.23.12 performs **1216 read syscalls** in one audit (about one
per installed package) and drags 166 MB through the squashfs block device, while
dpkg 1.23.11 performed 11 read syscalls and read 1.9 MB. On the live image that
read is decompressed in the calling process, which is where the 7.7-8.6 s of
dpkg's own CPU comes from. With the same admin directory on tmpfs the audit
costs 59 ms, so the cost is dpkg 1.23.12 x squashfs, not a Spaced configuration
problem. On an installed system the same command is expected to cost tens of
milliseconds; the 7 s is what the live image pays, and what our own VM checks
(`scripts/vm/qemu/live-checks.sh:395`, `scripts/vm/qemu/upgrade-test.sh:481`)
pay on every run.

## Idle desktop breakdown (one diagnostic boot per ISO, 60 s window)

CPU cost of the top processes while the live desktop is idle
(jiffies, 1 jiffy = 10 ms; 60 s window; one boot per ISO, and the two boots are
not comparable run to run - the 11.26 boot caught a busy stretch that the
11.26.1 boot did not, which is why the release-measure idle-CPU row above says
"same"):

| process | 11.26 jiffies/60 s | 11.26.1 jiffies/60 s |
|---|---|---|
| caja | 180 | 22 |
| nm-applet | 153 | 4 |
| mate-volume-control status icon | 145 | 23 |
| mate-settings-daemon | 105 | 1 |
| mate-panel | 99 | 1 |
| wnck-applet / notification-area / brisk-menu / clock-applet | 87 / 83 / 74 / 60 | 0 / 0 / 2 / 0 |
| compiz | 12 | 8 |

Short-lived processes (the `bwrap`/`glycin` chains below, `gsettings`, kworkers)
are not in this table: they exit before the second snapshot, so their CPU is not
attributed to a surviving PID.

Process churn over the same 60 s (distinct PIDs seen): 26 `bwrap`, 7
`glycin-image-rs`, 6–7 `glycin-svg`, 7 `gsettings` in **both** releases. The
`bwrap`+`glycin` chains are children of `mate-panel` and a panel applet: every
image the panel loads is decoded in a fresh bubblewrap sandbox. Consistent with
that, the idle session keeps reading the ISO: `/proc/diskstats` loop0 went from
761162 to 1376984 sectors (298 MiB, 84669 requests) during 60 s idle on 11.26,
and 779606 → 1356924 (279 MiB, 80148 requests) on 11.26.1.

## Measurement caveats

* The first six runs used a buggy CPU-jiffies reader in
  `scripts/vm/qemu/release-measure.sh` (bash reads `$12` as `$1` followed by
  `2`, so the sum was always 0). The script is fixed (`${12}`), but the
  `display_repair_cpu_jiffies_delta` column of the six runs is `0` for both
  releases and must be ignored. The wake-up conclusion rests on `nr_switches`
  (27 vs 0, identical in all three boots of each release) and on the reconcile
  `sleep` children.
* 11.26.1 run 2 was a slow outlier (SSH 30.5 s, desktop 36.9 s, uptime 18.03 s)
  while runs 1 and 3 were 26.4/31.7/15.2 and 26.4/31.7/15.18. That is why the
  boot-time rows are called "same".
* The live session is never fully idle: it keeps reading the ISO (see above),
  so "idle" numbers include that background work in both releases.
* `dpkg --audit` and `apt-get check` timings depend on the page cache; both are
  reported twice per boot (cold and warm) for that reason.
