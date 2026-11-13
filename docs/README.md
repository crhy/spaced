# Documentation index

Everything under `docs/`, in three groups. This index lists every Markdown file
directly in `docs/`; `notes/`, `troubleshooting/` and `releases/` have their own
folders.

## Using Spaced Linux

- [HELP.md](HELP.md) — help and community routes, and what a bug report needs.
- [UPGRADE.md](UPGRADE.md) — updating an installed system, what the update
  checks, and what to do when an update stops.
- [BOOTING.md](BOOTING.md) — the live boot chain, how it differs from stock
  Devuan, historical boot failures and their guards.
- [NVIDIA-RECOVERY.md](NVIDIA-RECOVERY.md) — the GPU driver manager: install,
  rollback, SSH recovery and the error-code table.
- `troubleshooting/` — one guide per reported problem:
  [218-virtualbox-installer.md](troubleshooting/218-virtualbox-installer.md),
  [227-default-uid-gid.md](troubleshooting/227-default-uid-gid.md),
  [desktop-app-integrations.md](troubleshooting/desktop-app-integrations.md),
  [network-servers.md](troubleshooting/network-servers.md).

## Working on Spaced Linux

- [README.md](README.md) — this index.
- [DESIGN.md](DESIGN.md) — current visual design principles for the Spaced
  identity and the OS-inspired themes.
- [SUBSYSTEMS.md](SUBSYSTEMS.md) — maintenance map connecting implementation,
  delivery and validation for each subsystem.
- [MATE-theming.md](MATE-theming.md) — canonical theming guide: component
  ownership, runtime switching, source-to-installed workflow, testing.
- [THEME-COLORS.md](THEME-COLORS.md) — inventory of the color-bearing parts of
  the desktop tree.
- [matepanel.md](matepanel.md) — panel applets, layouts, orientation, panel
  backgrounds and Cairo Dock.
- [COMPIZ.md](COMPIZ.md) — Compiz architecture, runtime behaviour, patches and
  upstream strategy.
- [APPLICATION-DELIVERY.md](APPLICATION-DELIVERY.md) — Welcome, SpacedBazaar,
  the signed Flatpak catalog, release pins and end-to-end tests.
- [FIXES.md](FIXES.md) — current resolutions of recurring issues across
  releases.
- [SESSION-REGRESSIONS.md](SESSION-REGRESSIONS.md) — session regression
  investigation for #198, #200 and #202.
- [DISPLAY-REGRESSIONS.md](DISPLAY-REGRESSIONS.md) — display and idle regression
  investigation for #189, #201 and #204.
- [RELEASE-CHECKLIST.md](RELEASE-CHECKLIST.md) — the maintainer's numbered
  release pass, from a clean tree to the deployed website.
- [VIDEO-INTRO-SCRIPT.md](VIDEO-INTRO-SCRIPT.md) — script and shot list for the
  introduction video; not shipped documentation.
- [VIDEO-SPACED-VOXA-SCRIPT.md](VIDEO-SPACED-VOXA-SCRIPT.md) — script for the
  Voxa feature video; not shipped documentation.
- `notes/` — working notes and standing decisions, indexed in
  [notes/README.md](notes/README.md).

## Release records

Per-release evidence, newest first. A review records what was tested at the time
and is not amended afterwards.

- [11.26.1-RELEASE-REVIEW.md](11.26.1-RELEASE-REVIEW.md) — candidate evidence
  for 11.26.1.
- [11.26.1-PAUSE-HANDOFF.md](11.26.1-PAUSE-HANDOFF.md) — exact state at the
  11.26.1 pause, including the required resume order.
- [11.26-RELEASE-REVIEW.md](11.26-RELEASE-REVIEW.md) — 11.26 publication review.
- [10.26.8-RELEASE-REVIEW.md](10.26.8-RELEASE-REVIEW.md) — 10.26.8 review,
  accepted with limited scope.
- [10.26.7-RELEASE-REVIEW.md](10.26.7-RELEASE-REVIEW.md) — 10.26.7 review.
- [10.26.6-POST-RELEASE-AUDIT.md](10.26.6-POST-RELEASE-AUDIT.md) — issue audit
  after the 10.26.6 publication.
- [10.26.6-RELEASE-REVIEW.md](10.26.6-RELEASE-REVIEW.md) — 10.26.6 review.
- [10.26.6-IMAGE-SIZE.md](10.26.6-IMAGE-SIZE.md) — squashfs block size and BCJ
  filter measurements.
- [10.26.6-DISTROWATCH-EMAIL.md](10.26.6-DISTROWATCH-EMAIL.md) — DistroWatch
  announcement draft.
- [10.26.5-ISSUE-STATUS.md](10.26.5-ISSUE-STATUS.md) — 10.26.5 source
  verification record.
- [10.26.4-ISSUE-STATUS.md](10.26.4-ISSUE-STATUS.md) — 10.26.4 issue
  verification.
- [10.26.3-TEST-PLAN.md](10.26.3-TEST-PLAN.md) — Samba sharing and AMD Xorg test
  plan.
- [10.26.3-ISSUE-STATUS.md](10.26.3-ISSUE-STATUS.md) — 10.26.3 issue
  verification.
- [10.26.2-ISSUE-STATUS.md](10.26.2-ISSUE-STATUS.md) — 10.26.2 issue
  verification.
- [10.26.2-ISSUE-PLAN.md](10.26.2-ISSUE-PLAN.md) — 10.26.2 draft issue plan.
- [10.26.1-ISSUE-STATUS.md](10.26.1-ISSUE-STATUS.md) — 10.26.1 issue
  verification.
- [10.26.1-IMAGE-SIZE.md](10.26.1-IMAGE-SIZE.md) — 10.26.1 image size audit.
- [9.26.3-ISSUE-STATUS.md](9.26.3-ISSUE-STATUS.md) — 9.26.3 issue status.
- [9.26.2-ISSUE-STATUS.md](9.26.2-ISSUE-STATUS.md) — 9.26.2 issue status.
- [9.26.1-ISSUE-STATUS.md](9.26.1-ISSUE-STATUS.md) — 9.26.1 issue status.
- [9.26-TESTING.md](9.26-TESTING.md) — 9.26 release validation.
- [9.26-DESKTOP-AUDIT.md](9.26-DESKTOP-AUDIT.md) — 9.26 desktop stability
  audit.
- [9.26-ISSUE-STATUS.md](9.26-ISSUE-STATUS.md) — 9.26 issue status.
- [8.26-TRIAGE.md](8.26-TRIAGE.md) — 8.26 issue triage.

`releases/10.26.6/` holds that release's announcement and change list, and
`font-comparison/` holds the font comparison artwork.
