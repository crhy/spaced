---
name: spaced-linux-version-scheme
description: "Spaced Linux releases are numbered month.year, so 9.26 is September 2026 and the release after 12.26 is 1.27, not 13.26."
metadata: 
  node_type: memory
  pinned: false
  originSessionId: 1e5c0034-f47b-4761-9ca0-96fc40a509fb
  modified: 2026-09-10T20:38:01.827Z
---

# Spaced Linux versions are month.year, not major.minor

A Spaced Linux release line is named for the calendar month and the
two-digit year it opens in. `9.26` is September 2026, `8.26` is August 2026,
`7.26` is July 2026. The number before the dot therefore never exceeds 12 and
wraps: the release after `12.26` is **`1.27`**, not `13.26`.

rhY corrected me on this after I wrote "roughly three or four major versions
out, so around 12.26–13.26" in a tracker issue: "there won't be a 13.26. it
will be a 1.27. the convention is based on year and month."

Do not read the leading number as a major version. Counting "three or four
releases ahead" of 9.26 gives 12.26 and then 1.27.

A line can slip a day or two past its month without being renamed — `7.26.5`
was published on 1 August 2026 and stayed in the 7.26 line.

## The rest of the number

Two further components sit below the line name:

- A patch release adds a third component, as in `9.26.1`. This is a new OS
  version: `VERSION`, `config/iso.yaml`, `overlays/etc/os-release`,
  `overlays/etc/lsb-release`, the Calamares branding, the GRUB entries and
  the live-build ISO name all carry it, and `scripts/check.sh` enforces that
  they agree.
- A Debian package revision adds `-N`, as in `9.26.1-3`. This ships fixes to
  installed systems through the APT repository without changing the OS
  version at all, because `packages/spaced-meta/DEBIAN/postinst` strips the
  revision before writing `/etc/os-release`. Use it for a fix that does not
  warrant a new ISO.

`VERSION_CODENAME` is the version with the dots removed, so `9.26.1` becomes
`9261`.
