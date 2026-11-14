---
name: spaced-11261-release-state
description: Spaced Linux 11.26.1 was published 2026-11-13; what is done, what is still open, and the elogind-upgrade session-loss defect found right after.
metadata:
  type: project
---
Spaced Linux 11.26.1 was published on 2026-11-13 about 15:15 PST: tag `v11.26.1` on `main` at `d6243eb`, ISO SHA-256 `937030fcb2103d5115ddda6d2e9ade497d239b1ff250352ee01bb34a734b1d6f`, APT repo `crhy/spaced-apt` at `bd42f00`, website live. Work happened in `/home/rhy/spaced1126` on branch `release/11.26.1`; every Strata task file and log is in `/home/rhy/SpacedStrataCommands/`, Strata's notes in `/home/rhy/spaced1126/.strata/out/`.

**Defect found after publishing (15:36):** updating a running 11.26 system upgrades the `elogind` package; the old package's prerm stops elogind and the new postinst starts it, which drops the desktop session and wipes `/run/user/<uid>`. Flatpak apps (Brave) then lose DNS ("no network"), audio breaks, until a reboot. It hit rhY's own PC (bigboy). The VM upgrade test (`scripts/vm/qemu/upgrade-test.sh`) passed all package checks but does not check session survival; its one FAIL was `update-grub` on a live ISO (test artifact).

**Finished the same day:** restart warning added to the release notes (Spaced Update shows them as "What's new"), docs and website; APT revision `11.26.1-2` published (`crhy/spaced-apt` `069d025`) with a session guard (`/usr/lib/spaced-linux/spaced-policy-rc.d` linked as `/usr/sbin/policy-rc.d`) so later elogind upgrades leave the running daemon alone, proven by `scripts/vm/qemu/session-guard-test.sh`; announcement posted as discussion #418; issues #415 #414 #413 #412 #409 #408 #407 #406 #397 #303 commented and closed; `main` and `release/11.26.1` at `ce05a83` or later.

**Still open:** (1) the guard cannot protect the one-time 11.26 to 11.26.1 update (the old package's prerm stops elogind before anything new is installed), so that update needs a restart; (2) rhY must enable "Private vulnerability reporting" on `crhy/spaced` (SECURITY.md points to it); (3) everything in `docs/ROADMAP.md`; (4) `scripts/vm/qemu/upgrade-test.sh` should gain a session-survival check; (5) no test ran on physical hardware except the update on rhY's PC.

**Why:** rhY made the release the top priority of the day and asked for publish + docs + announcement + issue closing.
**How to apply:** treat 11.26.1 as released; new fixes go on a branch for the next release or an APT revision `11.26.1-N`. Before publishing any package that upgrades elogind, run the session-guard test. Related: [[spaced-rhy-decisions-11261]].
