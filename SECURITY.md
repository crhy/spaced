# Security policy

How to report a security problem in Spaced Linux, what belongs in the report,
and how a fix reaches an installed system.

## Report it privately

Report a security problem through GitHub's **Report a vulnerability** form on
this repository:

<https://github.com/crhy/spaced/security/advisories/new>

That form is private; a public issue is not. Do not open a public issue for an
unfixed security problem, and do not post one in Discord or Telegram. Ordinary
bugs go through the issue tracker — see [CONTRIBUTING.md](CONTRIBUTING.md).

## What to include

- The Spaced version: the output of `cat /etc/os-release`.
- The affected component. For a native package, its package version:
  `dpkg-query -W -f='${Version}' <package>`.
- Whether it reproduces in a live session, on an installed system, or both.
- The exact steps that show the problem, and what an attacker gains from it.
- Any log, proof of concept, or patch you already have.
- Whether you want to be named in the advisory.

## What is in scope

- This repository: the `overlays/` filesystem, the Spaced Update components in
  `overlays/usr/lib/spaced-linux/`, the Calamares configuration, the APT and
  Flatpak integration, the packaging under `packages/`, and the build, ISO and
  release scripts.
- The components released from their own repositories and pinned in
  `config/external-artifacts.conf`: `crhy/spacedwelcome` (Welcome),
  `crhy/spacedmonitor` (Spaced Monitor), and `crhy/spacedbazaar` (SpacedBazaar
  and the signed `spaced-github` Flatpak catalog). Report a weakness there in
  that repository, or here if you cannot tell which one is at fault.
- The signed update repository `crhy/spaced-apt`, including its signing key and
  the metadata that Spaced Update trusts.
- The published ISO and the website source in this repository.

A weakness in Devuan, Debian or another upstream component belongs to that
project as well; say so in your report and send it upstream too.

## How a fix reaches users

The two delivery routes are described under "Release versioning" in
[AGENTS.md](AGENTS.md):

- A fix that needs no new image ships as a new Debian package revision: the OS
  version stays the same and the package gains `-N`, for example `11.26.1-2`.
  It is published to the signed APT repository, and installed systems receive it
  through Spaced Update.
- A fix that changes image content ships as the next patch release, a new OS
  version, with a new ISO.
- A component fixed in its own repository is released there, then pinned to the
  new tag and archive checksum in `config/external-artifacts.conf` for the next
  ISO build.

## Supported versions

Security fixes are prepared for the current release line only: **11.26**, with
**11.26.1** as its current patch release. Older release lines are not patched;
an installed system on an older line should be updated to the current one.
