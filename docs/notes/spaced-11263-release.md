---
name: spaced-11263-release
description: What must ship in Spaced 11.26.3 (milestone 11.26.3 on crhy/spaced): fire/screenshot fix, LUKS fix, Compiz video link.
metadata:
  type: project
---
Milestone `11.26.3` (crhy/spaced milestone 1) holds the fixes rhY wants in 11.26.3; merge their branches at release time (no PRs):
- #421 fire on Shift+Super + screenshots while fire is on: branch strata/fire-shift-super-and-screenshots-tested (= f050 + f054;
  rhY tested it on bigboy 2026-11-16 and it works). The release build of compiz-plugins-main must sort ABOVE 0.8.18-8+spaced11.26
  (the test deb rhY has installed), e.g. +spaced11.26.3.
- #420 LUKS boot: strata/f049-spaced-luks-boot-cryptroot (cryptsetup-initramfs).
- spacedbazaar#35 (milestone 11.26.3 in crhy/spacedbazaar): Bazaar offers AppImages and picks the best format; MUST
  default FreeCAD to the official AppImage (flatpak 1.1.4 freezes on Spaced; AppImage tested perfect 2026-11-16). Task f081.
- #425 FreeCAD flatpak freeze: ship system flatpak override QT_LOGGING_RULES=qt.accessibility.atspi=false (task f083;
  root cause FreeCAD NotificationArea self-deadlock, proven fix 2026-11-16; rhY's machine has it as a --user override).
- #158 Compiz video link in help: strata/f052-spaced-compiz-video-help-link (https://youtu.be/csKKNzKwrMg).
**Why:** rhY asked 2026-11-16 that these land in 11.26.3. **How to apply:** before tagging 11.26.3 check every milestone issue's
branch is merged, then close #421. Related: [[spaced-no-prs-batch-into-release]], [[strata-fleet]].
