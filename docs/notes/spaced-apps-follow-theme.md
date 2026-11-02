---
name: spaced-apps-follow-theme
description: rhY wants every Spaced app to take colours from the active desktop theme (navy for Win dark themes, grey for Spaced Dark/Mint, light for light themes), live; series th01-th06
metadata:
  type: project
---

rhY (2026-10-31): all custom Spaced apps must match like Spaced RGB and Spaced About (plain GTK widgets, no own colours):
grey under Spaced Dark / Spaced Mint (like Voxa, Spaced Update), navy under Windows themes with a dark-blue palette
(Win11-Dark #17243b, Win7Aero-Dark #182533), light under light themes, switching live and automatically. Spaced Update's
second header line is unreadable in some themes (subtitle forced to @theme_fg_color on the header). Bazaar does not switch.

Decision: rhY asked to port Voxa and Bazaar to GTK 3; Claude advised against (Bazaar ~75K lines C, 471 libadwaita calls,
GTK4-only widgets, loses upstream merges; Voxa 220 Adw uses) and queued the palette approach instead: the theme switcher
publishes ~/.config/spaced/libadwaita.css + theme.json, libadwaita apps load and watch it. Revisit only if rhY still
dislikes the shape differences.

Series: ~/strata-theme/tasks th01 Monitor follows theme, th02 Update subtitle contrast, th04 palette publisher
(spaced-switch-theme), th03 Welcome, th05 Voxa, th06 Bazaar (Claude builds the Flatpak after). Runner
~/strata-theme/run-theme-tasks.sh uses worktrees in ~/strata-theme/wt (never rhY's checkouts), commits but never pushes,
runs after q01-q04, then restores the Supermox backlog from ~/supermox-strata-backlog.theme-held.txt. Related:
[[spaced-monitor-issue385]], [[delegate-coding-to-local-qwen]].
