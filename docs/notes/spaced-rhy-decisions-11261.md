---
name: spaced-rhy-decisions-11261
description: Product decisions rhY made during the 11.26.1 release (licence, live ISO root login, rescue tools live-only, Samba, anacron, APT expiry).
metadata:
  type: project
---
Decisions rhY made on 2026-11-13 while releasing Spaced Linux 11.26.1:

- Licence: the project keeps the **rhY License 1.0** (`LICENSE`), not MIT. rhY insisted the line "if you use lawyers you're gay" stays; GNU GPL 3 or later is the stated fallback.
- The live ISO keeps root login over SSH and the root password must be obvious (a "Live session passwords.txt" on the live desktop, plus the help pages). Do not treat it as a security defect.
- Rescue tools (TestDisk, PhotoRec, ddrescue, smartmontools, lvm2, exfatprogs) **and GParted** are live-ISO only: the installer removes them and `spaced-meta` must not depend on the `rescue` group in `config/packages.yaml`.
- Samba file sharing listening from first boot is fine; leave it.
- `anacron` is part of the system (daily jobs on PCs that are off at night).
- The signed APT `Release` expires after 180 days (`SPACED_APT_VALID_DAYS`); republish at least that often.
- Strata does the heavy lifting to save Claude tokens; every task given to it is saved in `~/SpacedStrataCommands/`.

**Why:** rhY stated each of these directly. **How to apply:** do not re-open them; the audit roadmap (`docs/ROADMAP.md`) already treats live root SSH and Samba as intentional. Related: [[spaced-11261-release-state]].
