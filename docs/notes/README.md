# Project notes

Working notes, decisions and standing orders for this project, kept by Claude Code while working with rhY. Each file is one fact or decision; `[[name]]` links point to other notes (some live in other crhy repos' `docs/notes/`).

- [spaced-no-systemd](spaced-no-systemd.md): Spaced Linux is Devuan-based and sysvinit-only; systemd must never be introduced, and even naming it as a design reference is unwelcome.
- [spaced-never-means-never](spaced-never-means-never.md): On Spaced Linux, a user-facing "Never" setting must be absolute, even when honouring it costs related behaviour like the idle screen lock.
- [spaced-linux-dev-machine](spaced-linux-dev-machine.md): rhY's own workstation runs Spaced Linux, so Spaced changes can be verified here directly — on a private Xvfb display, never rhY's session.
- [spaced-linux-version-scheme](spaced-linux-version-scheme.md): Spaced Linux releases are numbered month.year, so 9.26 is September 2026 and the release after 12.26 is 1.27, not 13.26.
- [spacedrgb-lcd-ghosting](spacedrgb-lcd-ghosting.md): Lian Li GA II Vision LCD panel is faulty (holds images after 30 s); RMA advised. Spaced RGB got Clean LCD (10 min) and looping video (2026-10-31)
- [spaced-monitor-issue385](spaced-monitor-issue385.md): Standing order 2026-10-31: after the Strata vs Avalon A/B test, the winning engine builds Spaced Monitor (crhy/spaced#385)
- [spaced-apps-follow-theme](spaced-apps-follow-theme.md): rhY wants every Spaced app to take colours from the active desktop theme (navy for Win dark themes, grey for Spaced Dark/Mint, light for light themes), live; series th01-th06
- [spaced-theme-monitor-dies](spaced-theme-monitor-dies.md): Theme switching "broke" on rhY's PC because spaced-theme-monitor died silently (2026-10-31 ~11:10); fix th07 queued on theme-follow for the next Spaced release.
- [strata-vs-avalon-ab](strata-vs-avalon-ab.md): Strata vs Avalon A/B = both engines build Spaced Monitor from the same 9 tasks; setup, files and how to resume (2026-10-31)
- [notes-live-on-github](notes-live-on-github.md): rhY's rule (2026-11-01): all Spaced/theme data and every memory note must be on GitHub; upload each note to its repo's docs/notes/ right after writing it.
