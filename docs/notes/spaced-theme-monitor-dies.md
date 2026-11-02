---
name: spaced-theme-monitor-dies
description: Theme switching "broke" on rhY's PC because spaced-theme-monitor died silently (2026-10-31 ~11:10); fix th07 queued on theme-follow for the next Spaced release.
metadata:
  type: project
---
Found 2026-11-01: /usr/local/bin/spaced-theme-monitor (autostart, started once per login) exited after 2026-10-31 11:09:57; its `gsettings monitor` children were left orphaned (PPID 1). After that, picking a theme changes only the GTK theme; spaced-switch-theme extras (wallpaper, panel, dock, terminal, Flatpak, color-scheme) never run. Cause of the exit unknown: no log, no restart, syslog needs adm. Not earlyoom, not kernel OOM.

Fix = Strata task th07-theme-monitor-survives (~/strata-theme/tasks, runner ~/strata-theme/run-th07.sh, branch theme-follow in ~/strata-theme/wt/spaced-10.26-theme-follow, never pushed): --supervise restart loop, logger on every exit/signal, no orphans, clean up old orphans, catch up on restart.

**Why:** rhY: theme switching broke locally; wants the fix in the next Spaced Linux version.
**How to apply:** review th07's commit + gate; until a new session/version, a re-login (or starting the monitor in the session) restores switching. Related: [[spaced-apps-follow-theme]], [[spaced-no-systemd]].
