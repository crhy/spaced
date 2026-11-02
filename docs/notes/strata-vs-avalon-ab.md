---
name: strata-vs-avalon-ab
description: Strata vs Avalon A/B = both engines build Spaced Monitor from the same 9 tasks; setup, files and how to resume (2026-10-31)
metadata:
  type: project
---

rhY's call (2026-10-31): the A/B between Strata (coder-iq1_m) and Avalon (freriadoc/Avalon, llama.cpp fork, full
Qwen3.8-Flash-Next IQ3_KS, ~/Avalon, model ~/models/Qwen3.8-Flash-Next-Avalon-GGUF) IS building Spaced Monitor
(crhy/spacedmonitor, [[spaced-monitor-issue385]]). The winner's branch becomes main, then the winner builds the rest.

Setup in `~/spacedmonitor-ab/`: worktrees `strata/` (branch ab/strata) and `avalon/` (ab/avalon) from main 4223763;
`tasks/_header.md` + m01..m09; `ab-run.sh ENGINE` (pi window via strata-pi-send, gate, one fix-up, commit, ledger.csv);
`ab-all.sh` (waits for the current pi task, Strata phase, stops Strata, starts Avalon on :8080 in a window, smoke test,
Avalon phase). Logs: ab-all.log, run-*.log, avalon-server.log. Both at 64K context, same pi settings and limits.
Avalon local fix: CUDA must not pin experts (cudaHostRegister page-locks on NVIDIA) -> moe-cache.cu, git diff in ~/Avalon.
Supermox queue paused for it: backlog held in ~/supermox-strata-backlog.held.txt (restore after).

**Why:** pick the engine by real work, not benchmarks; rhY wants every step optimized.
**How to apply:** compare ledger.csv (gate pass, time, tokens, memory) + code review + screenshots vs mockups.
After: restore the Supermox backlog, restart Strata via the starter if Strata wins.

**Deadline and report (rhY, 2026-10-31 ~04:45):** both versions complete by late morning 2026-10-31, then a full comparison:
the code, code quality, efficiency (both the engines' tokens/time/memory AND the app's own CPU/RAM when running),
usability (does theme toggle, search, sort, end-app, tabs work), and how they look (screenshots vs the mockups, dark+light).

**Result (2026-10-31 06:30): Strata wins on this PC by default.** Strata: all 9 tasks passed (8 first try), 1 h 52 min.
Avalon cannot run usefully here: 88 GB model, 31 GB RAM, SATA SSDs only -> every prompt batch re-reads most experts from
disk (300 MB/s): prefill 3-13 tok/s (README 1,600), generation 6-9 tok/s (Strata 60-70). -b/-ub 9536 also OOMs a 16 GB
card (needs -ub 2048). Would need a fast NVMe (or ~96 GB RAM) to retest. Model still at ~/models (90 GB) unless deleted.
Then: Strata polishes its version (tasks p01/p02 in ~/spacedmonitor-ab/tasks) to become crhy/spacedmonitor main.
