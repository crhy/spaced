# Cross-OS benchmarks

Issue [#424](https://github.com/crhy/spaced/issues/424) asks for KVM benchmarks of
Spaced Linux against the 5-10 most popular operating systems, tabulated into
graphs, and adjustments until Spaced is first place. This document covers the
part that had to be built before any of that could happen: one probe that
measures any operating system the same way, one runner that walks a named matrix
of ISOs, and one comparator that turns the runs into a table and an SVG chart.

The nine-ISO matrix now exists and `run-bench.sh` sweeps it; what is still
open is listed in [What is not done](#what-is-not-done).

## The probe: `scripts/vm/bench/guest-probe.sh`

The probe prints `INFO: <metric>=<value>` lines for the machine it runs on. It
reads `/proc` and its own clock only: no package installs, no writes, no network,
no root, no display, and nothing Spaced-specific, so the same file can be copied
into a Spaced guest, a Debian guest or an Alpine guest and produce comparable
columns.

| Metric | Source | What it means |
|---|---|---|
| `uptime_at_desktop_ready_s` | `/proc/uptime` | the machine's uptime when the probe reaches the ready point |
| `mem_used_mib` | `/proc/meminfo` | `free(1)`'s used column: total − free − buffers − cached |
| `process_count` | `/proc/[0-9]*` | processes running |
| `top10_rss_kib` | `/proc/<pid>/status` `VmRSS` | resident memory of the 10 biggest processes |
| `settle_time_s` | `/proc/stat` `cpu` | first guest uptime after desktop-ready at which CPU in use stays under 1% for 10 s in a row; empty if it never settles before the window |
| `idle_sample_start_uptime_s` | `/proc/uptime` | the guest uptime the 60 s idle window actually started at |
| `idle_status` | derived | `ok` when the desktop was up by the fixed start point, `late` when it came later and the idle window was not measured |
| `context_switches_per_s` | `/proc/stat` `ctxt` | scheduler wake-ups per second over the idle window |
| `interrupts_per_s` | `/proc/stat` `intr` | interrupt counts per second over the idle window |
| `idle_cpu_percent` | `/proc/stat` `cpu` line | CPU percentage in use while idle, the same formula `scripts/vm/qemu/release-measure.sh` uses |
| `diskstats_reads_completed`, `diskstats_sectors_read`, `diskstats_mib_read` | `/proc/diskstats` | disk reads cumulative since boot, loop devices excluded |
| `pkg_manager`, `package_count`, `pkg_manager_query_ms` | `dpkg-query`, `rpm`, `apk` or `xbps-query`, whichever exists | which package manager the distro has, how many packages it holds, and how long that read-only count took |

The metric names are the ones `scripts/vm/qemu/release-measure.sh` already
reports, so a Spaced run and a Debian run land in the same TSV columns.

A metric the distro cannot provide is reported, never guessed:

```
SKIP: interrupts_per_s not available on this distro
```

`--selftest` measures the machine the script runs on with a short idle window,
which is how the probe is exercised without a VM:

```
bash scripts/vm/bench/guest-probe.sh --selftest
```

`--idle <seconds>` sets the idle window (default 60, or
`BENCH_PROBE_IDLE_SECONDS`). Exit codes: 0 = every metric emitted or explicitly
skipped, 1 = `/proc` is unreadable, 2 = bad arguments.

### The fixed idle point (task b03, issue #424)

rhY 2026-11-22 found the sweep's idle numbers were not comparable: task b02 saw
Spaced at 29.5% CPU sampled 11 s after boot but 0.05% at 180 s, because the old
probe sampled each OS at its own ready time — it was measuring each distro's
desktop autostart storm, not idle. The probe now starts the 60 s idle window at
the **same fixed guest uptime for every OS**: `BENCH_IDLE_START_UPTIME`
(default 300, equal to the runner's 300 s desktop timeout, so every OS that
booted is on its desktop by then). A distro whose desktop comes later than that
point is marked `idle_status=late` and not measured, rather than being sampled at
a different uptime. `settle_time_s` records how long after desktop-ready the
machine actually went quiet (polling `/proc/stat` every 1 s until CPU in use
stays under 1% for 10 s in a row), and `idle_sample_start_uptime_s` records the
uptime the window opened at. The Phoronix Test Suite set is run **after** this
idle window, so the benchmark never competes with the idle measurement.

## The sweep runner: `scripts/vm/bench/run-bench.sh`

```
bash scripts/vm/bench/run-bench.sh [MATRIX] [RUN-LABEL] [ONLY-LABELS]
```

For each entry in `scripts/vm/bench/matrix.conf` it boots the ISO in a **fresh
KVM VM** — `-enable-kvm -cpu host`, 4 vCPU, 8 GiB (`SPACED_QEMU_RAM` /
`SPACED_QEMU_CPUS` reach `common.sh`'s `build_common_args`), a 40G qcow2 virtio
disk under `/media/rhy/data/bench-vms/<label>/`, the same user-mode virtio NIC,
`-display none`, VNC and a QMP socket on 127.0.0.1 — measures it, writes one TSV
row to `build/bench/<label>-<run>.tsv`, and **destroys the VM and deletes its
disk directory before starting the next OS**. Only one benchmark VM is ever
alive, nothing about a run is left on disk, and the sweep refuses to start at
all unless `/media/rhy/data` has `BENCH_FREE_MIN_GB` (default 15) free, because
nine live ISOs and nine 40G images would otherwise fill the machine mid-run.
`/media/rhy/data/bench-vms/` is empty after a clean sweep — the gate checks
exactly that. The VM is stopped by the PID in the pidfile this run wrote, never
by name matching.

Most live ISOs offer no SSH server, so the guest is driven through the QMP
socket instead: `scripts/vm/bench/qmp-type.py` types one short command into the
live desktop's terminal (the shortcut that opens it is recorded per distro as
`terminal=` in `matrix.conf`; `ctrl-alt-t` on the MATE and Xfce live images),
which fetches `guest-probe.sh`, `guest-bootstrap.sh` and `guest-pts.sh` from
`scripts/vm/bench/http-report.py` — a host HTTP server on the `10.0.2.2` gateway
that serves those files and receives every result back as a POST into a
per-label inbox (a `curl -T` upload is a PUT, and the collector accepts it as
the same thing) — then runs them. The Spaced ISO answers SSH as well and uses
that path (`access=ssh`, root password `SPACED_LIVE_ROOT_PASSWORD` = `spaced`).
A QEMU 11 QMP `send-key` holds a chord only as long as the key list is pressed
together, so `qmp-type.py` sends chords (like `ctrl-alt-t`) as one multi-key
press and every other character as its own event. A live ISO still sitting at
its boot menu swallows a stray Tab/F2 and refuses to boot, so the runner taps
plain Enter for the first `BENCH_BOOT_MENU_TAPS` (3) rounds and types nothing
until the menu is behind it. `wget` is not in every live image (Debian's has no
`wget`), so the one typed command is `wget -qO- URL | sh`, `curl -s URL | sh`
or a `python3 -c` urllib fetch, whichever `fetch=` says.

Each row holds the probe metrics, the runner's own `boot_to_desktop_s` (VM start
to the moment the desktop answers), and a short **Phoronix Test Suite** run
inside the guest: `scripts/vm/bench/guest-pts.sh` installs
`phoronix-test-suite` with whatever the distro already has (`apt-get`, `dnf`,
`pacman`, `xbps-install` — no third-party repo is added). Debian and Devuan no
longer package it, so those fall back to the official upstream release (10.8.4)
plus `php-cli php-xml php-zip unzip build-essential`, which is what PTS itself
needs to unpack and build its tests; the fallback is recorded in the run log so
a version difference between distros is visible. It then runs
`batch-install`/`batch-run` over the recorded test set
with `BENCH_OS_CAP_SECONDS` as the per-OS cap, and posts back
`pts.tsv`, the PTS status and a tar of the PTS result files, so the comparator
can rank the same tests across distros and the raw PTS output survives the VM.

Three fixes to PTS 10.8.4 itself are part of that setup, all recorded in the run
log: PHP 8.4 makes `phodevi_memory` fatal on QEMU's non-numeric virtual DIMM
size, and the `load_dynamic_result_viewer` module is renamed out of PTS's module
directory because it forks a `php -S` result viewer and waits for a browser that
a headless live session never opens, which hangs every run before its first test.

The third fix is the one task b03 added, and it is why the first sweep produced
**no PTS number at all**: `guest-pts.sh` used to answer PTS's one-time batch
questions with `printf "\n\n\n..." | batch-setup`, i.e. every *default*, and the
defaults turn ON "prompt for test identifier", "prompt for test description",
"prompt for saved results file-name" and auto-upload. So `batch-benchmark`
printed the system-info block (spectre/vmscape lines) and then **hung waiting for
a test name** nobody typed; the host saw `captured=0 rc=124` at the cap, and
`pts/compress-zstd` etc. logged `no-result-line` / `run-failed-rc-143`. The fix
names every batch option *explicitly* (`PromptForTestIdentifier`,
`PromptForTestDescription`, `PromptSaveName` = FALSE, `SaveResults` = TRUE,
`UploadResults`/`OpenBrowser` = FALSE, `RunAllTestCombinations` = FALSE), marks
the suite configured, verifies the result by reading the `user-config.xml`
`batch-setup` wrote (10.8.4 has no `user-config-get` subcommand; as root the
file lands under `/var/lib/phoronix-test-suite`), hands the result
name/identifier/description through
`TEST_RESULTS_NAME`/`TEST_RESULTS_IDENTIFIER`/`TEST_RESULTS_DESCRIPTION`, and
runs the set with `batch-run` under a per-test timeout that logs
`STEP=install`/`STEP=run` so a hang names the step it was in. The option menu
`batch-run` still offers ("Multiple items can be selected…") is answered with
`1` (the first, short option — c-ray 1080p, zstd level 3): `/dev/null` and
empty lines are both *rejected* by that menu, and every rejected read re-prints
it forever (once into a 3.3 GB run log). The result each test writes is PTS's
own `composite.xml` — under the *system* result directory when the guest runs
as root, in a directory whose name strips the underscores from the result name —
copied into the `pts-results.tar`, and the `*-*-pts.tsv` row is read from it
(stdout has no stable result line: `compress-zstd` prints only its
`Average: … MB/s` blocks).

The sweep runs `pts/compress-zstd` plus short single-configuration CPU tests that
exist and build on every matrix family (sqlite/c-ray/openssl), all offline after
their install. The cap is measured from the desktop being reached, not from the
boot: a distro that spends minutes on `apt-get install build-essential` still
gets its tests, and the fixed idle window (300 s boot-to-desktop + a 60 s window)
runs before the tests, so the per-OS cap has to cover it. The full nine-OS sweep
is:

```
BENCH_OS_CAP_SECONDS=<measured> bash scripts/vm/bench/run-bench.sh \
    scripts/vm/bench/matrix.conf <run-label>
```

run in the background with its log polled; the measured per-OS run times and the
`BENCH_OS_CAP_SECONDS` they justify are recorded in `tasks/notes-b03-*.md` and
below once the sweep has been taken.

Every row also records the host's load average at the time it was measured and
whether the Strata engine (`pgrep -x strata`) was running, because a number
taken while the machine is doing other work is not comparable without saying
so.

A missing ISO or an OS whose desktop is never reached is reported, never
hidden:

```
SKIP: debian no iso at /media/rhy/data/bench-isos/debian-live-13.8.0-amd64-mate.iso
SKIP: zorin desktop never reached within 300s
RESULT: measured=7 skipped=2
```

Nothing is installed on the host, no package manager is run on the host, the
only host writes are under `build/bench/` and `BENCH_VM_DIR`, and the exit
status is 0 unless the arguments or the disk-free gate failed — a partial
matrix is a result, not a crash. `ONLY-LABELS` runs a named subset, which is
how a two-OS smoke test is taken without waiting for nine distros.

### The ISO matrix: `scripts/vm/bench/matrix.conf`

`matrix.conf` holds one
`<label> <iso-path> [distro=… version=… desktop=… access=ssh|qmp terminal=… rootcmd=… fetch=…]`
line per operating system, Spaced's own ISO first. Blank lines and `#` comments
are ignored, `{VERSION}` expands to the repo's `VERSION`, a relative path is
resolved against the repository root, and `+` stands for a space (the line is
word-split, so a literal space inside an option value would be lost). The nine
ISOs live under `/media/rhy/data/bench-isos/` on the benchmark machine, from
their official sources; this repository neither downloads nor installs another
operating system, and the ISOs are never committed:

| ISO | official source |
|---|---|
| `spaced-linux-{VERSION}-amd64.iso` | this repository's published release (`github.com/crhy/spaced`) |
| `debian-live-13.8.0-amd64-mate.iso` | `cdimage.debian.org` (Debian Live, MATE) |
| `linuxmint-22.3-mate-64bit.iso` | `linuxmint.com` download page |
| `Fedora-MATE_Compiz-Live-45-1.4.x86_64.iso` | `getfedora.org` (MATE Compiz spin) |
| `ubuntu-26.04.1-desktop-amd64.iso` | `ubuntu.com/download` |
| `Zorin-OS-18.1-Core-64-bit.iso` | `zorin.com/download` |
| `cachyos-desktop-linux-260809.iso` | `cachyos.org/download` |
| `void-live-x86_64-20250202-xfce.iso` | `docs.voidlinux.org/live/current` |
| `MX-25.3_Xfce_x64.iso` | `mxlinux.org/download` |

Adding a line is the last step, not the first: the image has to be fetched and
its checksum verified by hand, its terminal shortcut and package manager
recorded, before `run-bench.sh` can drive it.

## The comparator: `scripts/vm/bench/compare.py`

```
python3 scripts/vm/bench/compare.py [TSV ...] [--svg PATH]
```

Stdlib only — no PIL, no numpy, no matplotlib. With no arguments it reads every
`build/bench/*.tsv`. It prints one table per metric, marks the best value, and
puts `not measured` in every empty cell:

```
metric: mem_used_mib
| OS | value | note |
|---|---|---|
| spaced-linux | 1189 | best |
| debian | 1420 |  |
| freebsd | not measured |  |
```

It writes a bar chart to `build/bench/compare.svg` using the Spaced Linux Dark
metatheme colours, one block per ranked metric, the best bar the lighter one.

## What the comparator refuses to claim

A metric with data for fewer than two operating systems is not ranked:

```
REFUSED: mem_used_mib has data for 1 OS; ranking needs at least two
```

and those metrics are listed in the SVG as `not ranked, fewer than two OSes
measured:` so the chart cannot be read as a comparison that never happened.
`pkg_manager` is a name, not a number, so it is printed without a ranking. An
OS that was never measured appears as `not measured` in every column rather than
as a zero, and no "Spaced wins" conclusion is possible from a matrix that holds
only Spaced.

## Commands

- Probe on this machine: `bash scripts/vm/bench/guest-probe.sh --selftest`
- Full sweep, all nine ISOs (≈1 hour of VMs, run in the background and poll
  its log; nothing else should be running, and the row records whether it was):
  `bash scripts/vm/bench/run-bench.sh`
- Two-OS smoke test: `bash scripts/vm/bench/run-bench.sh scripts/vm/bench/matrix.conf 1 "spaced-linux,debian"`
- Compare and chart: `python3 scripts/vm/bench/compare.py`
- Tests (no QEMU started): `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_bench_matrix tests.test_bench_sweep`

## What is not done

These stay open on [#424](https://github.com/crhy/spaced/issues/424); nothing
here claims otherwise:

- **A complete sweep of all nine ISOs.** The full sweep has been taken in
  pieces: a subset smoke test is what proves the plumbing, and the Phoronix
  Test Suite set per OS is capped at `BENCH_OS_CAP_SECONDS` (1200) rather than
  run to completion, so the PTS columns hold whatever finished in time, not a
  full benchmark suite. Nine capped partial PTS runs are not a comparison yet.
- **The "adjust until we are 1st place" loop.** It cannot start before the
  measurements above exist; the comparator deliberately refuses to rank a metric
  only one OS was measured on.
- **Boot-time parity caveats.** The probe reports the machine's own uptime at
  ready time and the runner adds its own QEMU-start-to-desktop clock, but the
  desktop process names Spaced waits for (`mate-panel`, `caja`, `compiz`) do not
  exist everywhere, so the ready point is still chosen per distro from
  `matrix.conf`; until those are reviewed `boot_to_desktop_s` compares machines,
  not desktops.
- **Non-Linux and sh-only guests.** The probe assumes a Linux `/proc`; the
  operating systems #424 lists that do not have one need their own probe before
  they can be compared at all, and a guest whose live shell is not `bash`
  needs `guest-probe.sh` ported.

Booting nine distros also exceeds what a single release gate can wait for, so
`run-bench.sh` is meant to run in the background with its log polled, one ISO at
a time, and `compare.py` re-run over whatever rows landed.
