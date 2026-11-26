# Voxa integration: the supported v1 boundary

[#238](https://github.com/crhy/spaced/issues/238) asks for full Voxa integration
and [#283](https://github.com/crhy/spaced/issues/283) for a Voxa greeter in
Welcome. The 11.26.1 review kept both open and asked for one thing first: the
supported v1 boundary — which accounts and actions are local versus networked,
how credentials and transcripts are stored, what requires confirmation, how the
service starts and stops under sysvinit, and what works without a microphone or
network. This document is that boundary.

The same ask is recorded in three dated places — the [11.26.1 release review
open items](11.26.1-RELEASE-REVIEW.md), the [11.26.1 pause handoff](11.26.1-PAUSE-HANDOFF.md)
and the [10.26.6 post-release audit](10.26.6-POST-RELEASE-AUDIT.md). Those records are
not amended; this document is where the boundary they ask for now lives, and it must
not contradict them.

It is a gate, not an implementation promise. Nothing ships with it: no Voxa
code, no package, no service script, no autostart entry, no Welcome change.
Each section states the v1 rule and what v1 puts out of scope. Code may be
written only where a rule says v1 allows it, and only after the conditions in
the closing section hold.

Ownership stays where the [subsystem map](SUBSYSTEMS.md) puts it. Voxa's source
lives in `crhy/voxa` and reaches a machine as an independently released
application artifact, through the signed `spaced-github` Flatpak remote or
standalone Welcome — see [application delivery](APPLICATION-DELIVERY.md). This
repository owns the catalog entry and the desktop's side of any integration, and
holds no copy of Voxa's source. No Voxa package or dependency exists in
`config/packages.yaml` or in any `packages/*/DEBIAN/control`.

## 1. Accounts and actions: local versus networked

v1 rule: Voxa acts on the account of the user who started it, on that machine,
and nowhere else. An action is classified by where its effect lands, not by how
it was requested: a spoken request that writes outside the machine is a networked
action and follows the networked rules.

| Scope | In v1 | Out of scope for v1 |
|---|---|---|
| The user's own desktop session | Local. Open, minimize and restore applications, media and panel actions, work on files inside that user's own home. | Actions on another user's session, on root's account, or on a session the user did not start. |
| Local speech and inference | Local. On-device transcription, a local model backend reached over loopback, offline speech, reading the user's own configuration. | Installing or switching a model without saying so, or a remote model service. |
| A LAN service the user configured (Home Assistant) | Networked, opt-in, off until the user supplies an address and a token on that machine. Voxa's own tools refuse to act while those are unset and say what to set. | Acting on a LAN service the user has not configured, or holding an address or token for one they have not. |
| Network services (network speech, model downloads, web features) | Networked, opt-in, and reported as such. | Silent use: a networked feature that runs when the local path would have worked, or that reports success for work it did not do. |
| Third-party account logins (email, Telegram, YouTube, Discord, GitHub, Google Voice, Instagram) | Out of scope for v1. Voxa keeps no account and no credential for any of them. Voxa's existing mail behaviour is the model: it drafts and hands the draft to the user's own client, unsent, and never sends it. | Delegated authority, account tokens, posting, sending, replying or "connecting" an account on the user's behalf. |
| Another machine | Out of scope for v1. | Remote hosts, clusters, shared or server-side accounts, anything that survives this machine being wiped. |

## 2. Credentials and transcripts

v1 rule: per user, on that machine, inside that user's own files, and nowhere
else.

The precedent is already in Voxa's source. `voxa/config.py` keeps
`home_assistant_url` and `home_assistant_token` in the same `Settings` record
that the `ConfigStore` JSON file holds under the user's XDG configuration
directory; `voxa/agent/tools/home.py` refuses to act while they are unset and
names what to set instead of looking elsewhere.

- A credential is entered by the user, on that machine, into that user's own
  configuration file. It is never in an image, a Debian package, a Flatpak, a
  catalog entry, a descriptor, a launcher, a system-wide environment file, a
  screenshot, a log line, a transcript, or any file in this repository.
- Unset means unset: the feature says what is missing and does nothing.
- Backups keep that rule. Voxa's own backup policy replaces secret-looking
  values with `REDACTED-IN-BACKUP` and reports the redacted keys, so a restored
  machine asks the user to re-enter them. v1 keeps that behaviour.
- A transcript is a file the user owns. `voxa/agent/transcribe_file.py` writes
  the text beside the audio it read; v1 keeps that path and adds no copy: no
  shared transcript directory, no transcript database or index, no upload, no
  retention by the distribution, no copy readable by another user.
- Out of scope for v1: credential escrow or sync, a keyring or any shared
  credential store, transcript search across machines or users, cloud storage,
  and any second copy of either outside the user's own files.

## 3. What requires confirmation

v1 rule: the existing risk ladder decides, and nothing lowers it.

`voxa/agent/policy.py` defines `RiskLevel` (`READ_ONLY`, `REVERSIBLE`,
`EXTERNAL_WRITE`, `SENSITIVE`) and `needs_confirmation()`: levels 0-1 act
without asking, level 2 asks unless that tool is in the user's granted set,
level 3 always asks.

- Read-only and reversible actions act immediately.
- An external write — anything that changes state on a service or another
  machine — asks, and keeps asking until that user grants that specific tool in
  their own configuration. A grant belongs to one user, one tool, one machine,
  is visible in that user's configuration, and is never created by an install,
  an update, a catalog entry or a Welcome release.
- A sensitive action always asks. There is no setting that turns this off.
- Confirmation is answered by the user in Voxa's own window. A notification, a
  log line, a background process or a remote service never answers it.
- Out of scope for v1: granting a class of tools, granting by default, one
  confirmation that applies to later actions on another machine, and any
  confirmation Voxa would answer for the user.

## 4. Service lifecycle under sysvinit

v1 rule: Voxa is an application the user starts, not a service the machine
starts. There is no Voxa service script in v1.

If a background helper is ever needed, it follows the two service scripts this
tree ships, `overlays/etc/init.d/spaced-first-boot-snapshot` and
`overlays/etc/init.d/spaced-wsdd`: an LSB `### BEGIN INIT INFO` block with
explicit runlevels, `start|stop|restart|force-reload|status`, `start-stop-daemon`
with a pidfile under `/run`, a drop to an unprivileged user (`spaced-wsdd`
uses `--chuid nobody:nogroup`), `exit 0` when the program is absent, and a
`status` branch that reports the truth. `stop` leaves nothing running and no
pidfile behind. `scripts/check.sh` fails the build if an init-system-named
package other than the two standalone sysusers and tmpfiles utilities the image
already carries enters the image set, so a Voxa helper must not disturb that
either.

Lifecycle independence in v1:

- No Voxa package or dependency in `config/packages.yaml` or in any package's
  dependency list. What this tree ships for Voxa is discovery and an on-demand
  shortcut only: the `io.github.crhy.voxa` row in the SpacedBazaar catalog,
  the Ctrl+Alt+V shortcut that runs `spaced-hotkey-action voxa` and then
  `spaced-open-target io.github.crhy.voxa`, and a bookmark seed. The shortcut
  reports `Shortcut target not found` when Voxa is not installed. Voxa arrives
  only as an application artifact the user installs.
- Voxa is not a lifecycle dependency of the desktop session or of Welcome.
  Boot, login, Xorg, the panel, Welcome and Spaced Update must behave the same
  with Voxa installed, uninstalled, running, stopped or crashed.
- Stopping Voxa must never stop or restart the login service or the desktop
  session. The `spaced-policy-rc.d` session guard in [FIXES.md](FIXES.md)
  already makes that rule absolute for package updates; Voxa does not get a
  new way around it.
- Out of scope for v1: a Voxa init script, a runlevel link, an autostart entry
  installed by the distribution, a Voxa process that outlives logout or starts
  at boot, a Voxa dependency in the desktop session's start path, and any
  change to boot order.

## 5. What works with no microphone and no network

Works with no microphone in v1: the application starts and shows its state;
transcription of an audio file already on disk; local inference and local file
work; desktop actions; reading and editing the user's own configuration.

Works with no network in v1: on-device transcription, a local model backend on
loopback, spoken replies through the offline speech fallback Voxa already
documents, desktop actions, local file work, and its own configuration. Voxa's
own README calls this local-first, not local-only; v1 keeps that wording honest
by naming which features need the network.

What must say so honestly instead of pretending:

- No microphone: it says it cannot hear and does nothing that needs hearing.
  It never pretends to listen, and never reports an answer it did not get.
- No network: network speech, model downloads and web features report that
  they are unavailable. They do not return empty results as success, and they
  do not substitute a worse path without saying which one they used.
- A missing model, backend, microphone or credential is named, with what to
  do about it. Voxa's own architecture notes treat these as expected failures
  that must not crash the application; v1 keeps them non-crashing and explicit.
- Voxa not installed: the shipped Ctrl+Alt+V shortcut says its target is not
  found. It installs nothing and reports no success.
- OFFLINE is a real boundary: listening stops, work in flight is cancelled, and
  nothing resumes it silently.
- Out of scope for v1: shipping a microphone default or choosing an input
  device for the user, installing a model automatically, and any silent remote
  fallback when the local path fails.

## 6. When #283 and a desktop-session dependency may be attempted

All of these conditions must hold first.

1. Voxa's v1 feature set is measured working on a real Spaced machine:
   microphone capture, on-device transcription, a local backend, desktop
   actions, and honest failure when any one of them is missing. Only measurement
   on a real PC settles this.
2. The credential and transcript rules in section 2 are implemented in
   `crhy/voxa` and verified: nothing leaves the machine, and an unset credential
   does nothing.
3. The confirmation policy in section 3 is implemented and visible: every
   external write and every sensitive action asks the user.
4. Voxa is proven not to affect boot, login, the panel, Welcome or Spaced
   Update, including a crash and an uninstall. Any claim about a full-machine
   problem needs kernel and memory evidence, as the subsystem map requires;
   Voxa is not blamed without it.
5. The version being integrated is published to the signed `spaced-github`
   Flatpak remote, or released as Welcome, with the pin staged and verified
   the way [application delivery](APPLICATION-DELIVERY.md) describes.
6. The greeter's own scope is agreed: what it says, what it may install, and
   that a user who declines it gets the ordinary Welcome path unchanged.
7. Each repository's half has a named owner, and each change comes with a test
   that fails before the change and passes after it.

Those conditions are not met in v1. Until they are, this document is the gate:
#238 and #283 stay open, Voxa stays out of the default install, and no part of
the desktop session or of Welcome depends on it.
