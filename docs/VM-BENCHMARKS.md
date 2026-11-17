# Cross-OS benchmarks

Issue [#424](https://github.com/crhy/spaced/issues/424) asks for KVM benchmarks of
Spaced Linux against the 5-10 most popular operating systems, tabulated into
graphs, and adjustments until Spaced is first place. This document covers the
part that had to be built before any of that could happen: one probe that
measures any operating system the same way, one runner that walks a named matrix
of ISOs, and one comparator that turns the runs into a table and an SVG chart.

The distro matrix itself is **not** done; see [What is not done](#what-is-not-done).

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

`--idle <seconds>` sets the idle window (default 10, or
`BENCH_PROBE_IDLE_SECONDS`). Exit codes: 0 = every metric emitted or explicitly
skipped, 1 = `/proc` is unreadable, 2 = bad arguments.

## The runner: `scripts/vm/bench/run-bench.sh`

```
bash scripts/vm/bench/run-bench.sh [MATRIX] [RUN-LABEL]
```

For each entry in `scripts/vm/bench/matrix.conf` it boots the ISO in KVM through
`scripts/vm/qemu/common.sh`'s `build_common_args` (`-enable-kvm -cpu host -m
4096 -smp 4` plus the forwarded SSH port), copies `guest-probe.sh` in over that
port with `scp`, runs it, and writes one TSV row to
`build/bench/<label>-<run>.tsv`. The VM is stopped by the PID in the pidfile
this run wrote, never by name matching.

An entry whose ISO is not on this machine is announced and the run continues:

```
SKIP: debian no iso at /home/…/spaced/build/iso/bench/debian-13-amd64.iso
…
RESULT: measured=1 skipped=4
```

A partial matrix is always visible; the runner exits 0 because "no ISO here" is
a fact, not a failure. Nothing is installed, no package manager is run on the
host, and the only writes are under `build/bench/`.

Two things another distro has to allow for its row to appear at all: it must
accept root login over the forwarded SSH port with `SPACED_LIVE_ROOT_PASSWORD`
(default `spaced`) or its own password set in that variable, and it must have
`bash` for the probe to run in. A distro that refuses either shows up honestly
as `SKIP: <label> no SSH on port <port> within <timeout>s` or
`SKIP: <label> probe failed in the guest`; a `sh`-only probe for, say, Alpine
is still open work.

### Adding a distro

`matrix.conf` holds one `<label> <iso-path>` line per operating system, Spaced's
own ISO first. Blank lines and `#` comments are ignored, `{VERSION}` expands to
the repo's `VERSION`, and a relative path is resolved against the repository
root.

```
spaced-linux build/iso/spaced-linux-{VERSION}-amd64.iso
debian build/iso/bench/debian-13-amd64.iso
```

Adding the line is the last step, not the first: the image has to be fetched,
its checksum verified and its path recorded by hand, because nothing in this
repository downloads or installs another operating system.

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
- Whole matrix: `bash scripts/vm/bench/run-bench.sh`
- Compare and chart: `python3 scripts/vm/bench/compare.py`
- Tests (no QEMU started): `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_bench_matrix`

## What is not done

These stay open on [#424](https://github.com/crhy/spaced/issues/424); nothing
here claims otherwise:

- **The 5-10 distro ISO matrix.** No image of any other operating system exists
  on the machine this work was done on, and its network reaches only
  `github.com` and `mirror.hootsoftware.com`; `deb.xlibre.org`, `xlibre.org` and
  the general web return no connection at all. No ISO was fetched, and `matrix.conf`
  therefore lists only Spaced plus commented example lines.
- **Installing and booting those distros.** Only the plumbing exists: the boot,
  copy-in and probe steps have never run against a non-Spaced guest, so no
  number in this document comes from another operating system. The probe also
  assumes a Linux `/proc`; the operating systems #424 lists that do not have
  one need their own probe before they can be compared at all.
- **The "adjust until we are 1st place" loop.** It cannot start before the
  measurements above exist; the comparator deliberately refuses to rank a metric
  only one OS was measured on.
- **Boot-time parity caveats.** The probe reports the machine's own uptime at
  ready time rather than a QEMU-start-to-desktop clock, because the desktop
  process names Spaced waits for (`mate-panel`, `caja`, `compiz`) do not exist
  elsewhere. A later pass has to decide the ready point per distro; until then
  `uptime_at_desktop_ready_s` compares machines, not desktops.

Booting ten distros also exceeds what a single release gate can wait for, so
`run-bench.sh` is meant to run in the background with its log polled, one ISO at
a time, and `compare.py` re-run over whatever rows landed.
