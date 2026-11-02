---
name: spaced-monitor-issue385
description: Standing order 2026-10-31: after the Strata vs Avalon A/B test, the winning engine builds Spaced Monitor (crhy/spaced#385)
metadata:
  type: project
---

rhY's order (2026-10-31): once the Strata vs Avalon A/B test is done, have the **winner** build **Spaced Monitor**, crhy/spaced issue #385: "a beautiful system monitor that shows CPU, GPU, RAM, basically everything btop or nvtop show, all in one window, much easier to understand. Rich colors on gauges, easy to read temperature graphs. The prettiest task manager EVER."

Two mockups (issue comments; copies in `~/spaced-10.26/.strata/issue385/`): tabs Overview / Processes / Hardware, dark + light theme; gauge cards CPU, GPU, Memory (Apps/Cache/Available bar), GPU memory (+swap); 5-minute CPU/GPU temperature graph with 80 °C line; disk read/write + storage; network up/down sparkline; "What is using your computer?" process table (CPU/RAM/GPU/Disk bars, search, filter) with a red ✕ per row to end a process; footer fans RPM, CPU power, GPU power, uptime.

**Why:** next Spaced Linux app; also the real-world workload for the engine A/B.
**How to apply:** follow Spaced rules (sysvinit only, lean, Flatpak-primary, components are separate repos; see spaced-10.26/AGENTS.md). The engine does the code via pi tasks; Claude plans, writes task files, reviews, gates. Related: [[delegate-coding-to-local-qwen]], [[spaced-no-systemd]], [[strata-ram-budget]].

Repo: **crhy/spacedmonitor** (public, GPL-3.0, created by rhY 2026-10-31), local `~/spaced-10.26/components/spacedmonitor`. Plan: native .deb, Python + GTK3 + Cairo, data from /proc, /sys hwmon and nvidia-smi.

**Status 2026-10-31 07:50:** built by Strata (14 tasks) + Claude fixes from real-app runs; merged to main 86c540c and
pushed; .deb built (build/spaced-monitor_0.1.0_all.deb, not yet in spaced-apt or the ISO). Report:
https://claude.ai/artifact/CEV2jHQ5St7PPTaygRMhXm . Open items: theme button icon "●", round logo, NVML instead of
nvidia-smi spawns (5% CPU), app names/icons, fans need nct6775, CPU power needs root. Gate now has tests/ui_live.py
(real window + real samplers) and tests/test_real_sampler.py.

**rhY's feedback after trying it (2026-10-31 ~10:50):** "pretty great". Wants: ✕ ends the app IMMEDIATELY, no
confirmation dialog (SIGTERM then SIGKILL); ✕ always red; Overview list sortable by CPU/RAM/GPU/Disk like the Processes
tab and scrollable; middle section smaller, process list bigger; draggable bars between sections; whole window shrinkable
much smaller incl. the top section; no "S" logo at all; plus the known rough edges (theme icon, names/icons, NVML).
Queued as Strata tasks q01-q04 in ~/spacedmonitor-ab/tasks via ~/spacedmonitor-ab/sm-fixes.sh (runs after Supermox t76,
then restores the Supermox backlog).

**Sensors (2026-10-31):** fan chip on rhY's TUF X670E is NCT6799 -> `nct6775` loaded and added to /etc/modules (fan2 =
pump ~2,730 RPM; the Lian Li fans hang off the cooler hub, not the board). CPU power: rhY chose to let every user read
RAPL: Spaced Monitor's .deb ships /usr/lib/udev/rules.d/60-spaced-monitor-rapl.rules + postinst chmod 0444
(commit c20ae8b on ab/strata). Not shipped: auto-loading nct6775 on other installs (not asked).

**Standing order (rhY, 2026-10-31 ~12:10):** once Spaced Monitor is polished (q03-q05, q06 layout-final, th01 and q07 final-polish done; check the 4-size screenshots), review the
screenshots, run the gate, merge ab/strata into main, PUSH to crhy/spacedmonitor, build the .deb and INSTALL it on rhY's
machine (sudo apt install ./build/spaced-monitor_*_all.deb). Fix real problems first rather than install something broken.
