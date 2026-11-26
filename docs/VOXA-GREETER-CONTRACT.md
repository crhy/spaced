# Spaced Welcome Voxa greeter: the staged contract

[#283](https://github.com/crhy/spaced/issues/283) asks for an AI greeter inside
Spaced Welcome that walks a new user through the install: a large two-button
chooser, a spoken welcome, `voxa quit` as the escape, sound calibration that also
drives the speakers and the adaptive noise cancellation, applications installed
"in the background while the sound calibration is going on", a browser offer with
a nine-logo chooser, a 3-4 minute training session, and an optional 10-30 minute
tutorial that installs applications, hooks MCPs and teaches voice control of
email, documents, video, games and 3D printing.

The 11.26.1 review kept that issue open and asked for one thing first, verbatim:

> Before implementation, we need a staged contract for offline/online behavior,
> microphone consent and retention, model selection/resource limits, accessibility
> and a no-audio path, privileged hardware/app-install actions, cancellation/rollback,
> service lifecycle, and ownership between Welcome and Voxa. I recommend the first
> milestone be an explicitly opt-in greeter that performs no privileged or
> background installs until the user approves a visible plan; calibration and
> tutorials can follow behind tested APIs.

The same ask is recorded in the [11.26.1 release review](11.26.1-RELEASE-REVIEW.md)
open items ("Spaced #283 and #238, Voxa integration | Long-term component/product
work, larger than a stability patch. | Define supported voice features, privacy
model, service lifecycle and packaging ownership."), in the
[11.26.1 pause handoff](11.26.1-PAUSE-HANDOFF.md), and the
[10.26.6 post-release audit](10.26.6-POST-RELEASE-AUDIT.md) still lists #283 as
pending. Those dated records are not amended. This document is where the staged
contract they ask for now lives.

**This is a gate, not an implementation.** Nothing ships with it: no greeter code,
no package, no service script, no autostart entry, no Welcome change, no behaviour
change of any kind. The greeter itself is not in this repository and cannot be
written here. Per the [subsystem map](SUBSYSTEMS.md) Welcome row and
[application delivery](APPLICATION-DELIVERY.md), `crhy/spacedwelcome` "publishes the
`spaced-welcome` Debian package. It owns the Welcome executable, desktop and
autostart files, application list, and installation workflow", and "Welcome changes
need a Welcome release". Every milestone below is therefore implemented in
`crhy/spacedwelcome` and stays blocked behind the rule it names here. This
repository owns the contract, the release pin, and the desktop's side of the
boundary.

## 1. Milestones and what unlocks each

The first milestone is named exactly as the review recommends: **an explicitly
opt-in greeter that performs no privileged or background installs until the user
approves a visible plan.** A milestone is unlocked only by the *tested* API of the
milestone before it — a tested API means a run on real hardware with the observed
result recorded in the change, not a design sketch.

| Id | Milestone | Requires (unlocked by) | Unlocks | Ships in |
|---|---|---|---|---|
| M0 | Opt-in chooser | nothing; it is the entry point, and the old welcome stays the default | M1 | `crhy/spacedwelcome` → `spaced-welcome` Debian package |
| M1 | Tested hardware report | M0 shipped and chosen by a real user | M2 | `crhy/spacedwelcome` |
| M2 | Consented calibration | M1 report measured on real hardware | M3 | `crhy/spacedwelcome` |
| M3 | Approved install plan | M2 consent path tested | M4 | `crhy/spacedwelcome`, plus this repository's pin bump |
| M4 | Brief training session | M3 plan applied on a real machine | M5 | `crhy/spacedwelcome` |
| M5 | Long tutorial | M4 shipped; every tutorial step is itself an approved plan | — | `crhy/spacedwelcome`, with catalog entries from `crhy/spacedbazaar` |

Each milestone states what it may do, what it may never do, the exact consent
prompt the user sees and hears, what it stores and where, its retention rule, its
resource ceiling, its cancellation and rollback behaviour, and its
no-hardware/no-audio path.

State convention for all milestones: the greeter's own record is
`$XDG_CONFIG_HOME/spaced-welcome/greeter.json`, created mode 600, owned by the
user who ran it, and replaced rather than appended to. Transient capture lives
under `$XDG_RUNTIME_DIR/spaced-welcome-capture/` (directory mode 700, files mode
600) and is unlinked when the milestone ends. A visible **Forget** action in the
greeter deletes every one of those files and says so. Nothing is written to a
system-wide path, to another user's files, or into an image or package.

### M0 — Opt-in chooser

- **May do:** show the two large buttons **Old Spaced Welcome** and **New Voxa
  Spaced Welcome**, pointer-selectable; play pre-recorded clips that ship inside
  the `spaced-welcome` package; accept `voxa quit` as an escape; hand off to the
  current Spaced Welcome unchanged.
- **May never do:** open the microphone, contact the network, install anything,
  write anything outside its own state file, or make the new welcome the default.
- **Consent prompt (shown and spoken, verbatim):** "Welcome to Spaced Linux."
  then "Please select which welcome to launch." then "The Voxa Spaced Welcome
  will not install anything until you approve a plan." Answers: **Old Spaced
  Welcome** / **New Voxa Spaced Welcome**, plus a visible **Quit to the old
  welcome** button equivalent to saying `voxa quit`.
- **Stores:** the single choice, in `greeter.json`.
- **Retention:** kept until the user changes it; deleted by **Forget**. No timing,
  no audio, no hardware detail.
- **Resource ceiling:** no model at all; no inference; no download. Clip playback
  only, under 10 MiB of shipped media.
- **Cancellation and rollback:** any answer other than **New Voxa Spaced Welcome**
  ends the milestone; nothing has changed, so there is nothing to roll back.
- **No-hardware/no-audio path:** the chooser works with keyboard and pointer alone
  and with the speakers off; every spoken line above has the same text on screen.

### M1 — Tested hardware report

- **May do:** read the audio and peripheral devices the desktop already sees
  (card, sink, microphone presence, speakers, displays, input devices) using the
  read-only side of what this tree already ships, and show the user a plain-language
  report of what was found and what is missing.
- **May never do:** capture audio, change a setting, load or build a driver,
  run a privileged helper, or infer that a device works because it is listed.
  A VM result is not evidence about real hardware; the [subsystem map](SUBSYSTEMS.md)
  says so for the display and GPU rows and it applies here too.
- **Consent prompt:** "Voxa will describe the audio hardware it found. It will not
  change any setting." Answers: **See the hardware report** / **Skip the report**.
- **Stores:** device names, IDs and capability flags in `greeter.json`.
- **Retention:** recomputed on every run; the previous record is replaced. Never
  contains audio or a transcript.
- **Resource ceiling:** no model, no inference, no download; the report must render
  in under 5 seconds and must not start a helper that outlives the greeter.
- **Cancellation and rollback:** **Skip the report** ends the milestone and M2 stays
  locked. Nothing to roll back.
- **No-hardware/no-audio path:** when no microphone or no speaker is found, the
  report says which is missing and M2 is presented as unavailable rather than
  failing; the greeter continues on text.

### M2 — Consented calibration

- **May do:** with an explicit yes, capture the user's voice, measure input level
  and intelligibility, play test output through its own player, ask which output
  level the user prefers, and store the derived numbers for Voxa to use later.
- **May never do:** keep the capture after the milestone ends, upload it, tune
  another application's volume or microphone gain, or tune the adaptive noise
  cancellation in real time as the issue describes — that behaviour belongs to the
  Voxa runtime, which only an approved plan may install, so it moves to M3 and
  later. The cost of that ordering is stated here and not softened.
- **Consent prompt:** "To hear you clearly, Voxa needs a sound calibration. It
  will play test sounds out loud and listen through your microphone. It keeps no
  recording. Is that OK?" Answers: **Yes, calibrate my sound** / **No, keep my
  microphone off**. On **No** the greeter says, and shows: "OK, Voxa will not work
  as well. You can come back any time and say 'Voxa, let's calibrate sound.'"
  (the issue's wording, with the spelling corrected).
- **Stores:** derived numbers only — measured input level, the user's preferred
  output level as a proposal, frequency-band hints. Never the capture itself.
- **Retention:** capture lives only under `$XDG_RUNTIME_DIR/spaced-welcome-capture/`
  and is unlinked when the milestone ends, including on crash and on cancel. On
  **No**, nothing at all is written. Numbers are deleted by **Forget** and never
  re-enable capture.
- **Resource ceiling:** no model download; local speech only, and if no local
  model is present the milestone runs on its shipped clips and on-screen text.
  Capture is bounded to the calibration prompts, at most 90 seconds of audio in
  total, and is never concurrent with a download or an install.
- **Cancellation and rollback:** `voxa quit`, **Stop**, or a timeout at any point
  ends the milestone, deletes the capture, and leaves the previous state intact.
  A failed capture (device busy, wrong card, no input) is reported as a failure;
  the greeter does not retry silently and does not claim a calibration it did not
  do.
- **No-hardware/no-audio path:** with no microphone, M2 is unavailable and the
  greeter says so; with the user declining, every later milestone that needs
  calibration runs in its text form. The keyboard path always exists.

### M3 — Approved install plan

- **May do:** show a plan the user can read — one row per action, naming the
  application, its origin (Flathub, the signed `spaced-github` remote, or APT),
  its scope (user or system), and the size the registry reports — and act only on
  rows the user approved. This is where Voxa, Ollama, the default model and the
  browser offer from the issue land.
- **May never do:** start any install or download before that plan is approved,
  run one in the background while another milestone is running, install by resolving
  a mutable GitHub "latest release" bundle instead of an app ID from a signed
  origin, or run an APT transaction that bypasses the guard at
  `overlays/usr/lib/spaced-linux/spaced-update-apt-guard`, which already refuses a
  transaction that would change the sysvinit system or remove a core Spaced package.
- **Consent prompt:** "Voxa has a plan for what to install. Read it first." Answers:
  **Install this plan** / **Change the plan** / **Do not install anything**. The
  browser row is added only after its own question: "You probably want a browser
  to surf the web. May Voxa install the Spaced default browser, Brave, for you?"
  and on **No**: "Which browser would you like?" followed by a chooser screen of
  nine browsers taken from the signed catalog. The default browser is whatever
  this repository's `overlays/usr/share/applications/mimeapps.list` names as the
  http/https handler, currently `com.brave.Browser.desktop`.
- **Stores:** the applied plan as a manifest in `greeter.json`, naming refs and
  versions, so rollback is possible.
- **Retention:** the manifest is kept until the plan is rolled back or the user
  purges it; it holds no user content.
- **Resource ceiling:** one install or download at a time, never concurrent with
  capture or inference; the default model is `qwen2.5:0.5b` and it is the ceiling
  for M0-M4; the plan must state the model's reported download size and the free
  space measured on the target, and must refuse a download that does not fit
  (Calamares already requires 5 GB of storage in
  `overlays/etc/calamares/modules/welcome.conf`).
- **Cancellation and rollback:** **Do not install anything** leaves the system
  exactly as it was. Cancelling mid-plan stops after the current row, reports
  which rows completed and which did not, and offers an explicit **Undo what
  Voxa installed**, which removes only the refs named in its own manifest and
  nothing the user installed themselves. A failed download or install leaves the
  previous state intact, says what failed and from which origin, and offers a
  retry the user must choose.
- **No-hardware/no-audio path:** the plan is a screen the user reads and answers
  with the pointer; nothing in M3 requires a microphone.

### M4 — Brief training session

- **May do:** run a short session, at most 4 minutes as the issue requires, that
  demonstrates what is already installed and working: navigation by pointer and
  by voice, enhanced zoom, opening a document, taking a screenshot.
- **May never do:** install anything that M3's approved plan did not already
  cover, extend itself past 4 minutes, or record what the user says during the
  session.
- **Consent prompt:** "Would you like the short Spaced Linux training session?
  It takes up to 4 minutes." Answers: **Start the training** / **Not now**.
- **Stores:** a completion flag only.
- **Retention:** nothing said during the session is stored; no transcript is written.
- **Resource ceiling:** one inference request at a time, one model process, a
  90-second wall clock per spoken exchange with a visible timeout, and a 4-minute
  total. If the model is absent or the download failed, the session runs entirely
  from shipped clips and on-screen text and says which model is missing and what
  it would have downloaded.
- **Cancellation and rollback:** `voxa quit` or **Stop** ends the session at once;
  nothing was changed, so nothing is rolled back.
- **No-hardware/no-audio path:** the session is captioned and every step has a
  pointer equivalent; it completes with the speakers off.

### M5 — Long tutorial

- **May do:** run the 10-30 minute tutorial the issue describes, one approved
  step at a time: applications for photo and video work, larger models and MCP
  hooks, email, dictation and document editing, screen recording and editing,
  games, screenshots and image editing, CAD and 3D printing.
- **May never do:** treat the tutorial as one bulk install. Every application,
  model, MCP hook and printer integration is its own M3-style plan row with its
  own approval, and a yes earlier in the tutorial never carries over to a later
  step. It never creates a credential, an account token or a delegated authority
  for the user, and it never sends, posts or replies on the user's behalf.
- **Consent prompt:** "Would you like a more detailed tutorial? It can take 10 to
  30 minutes, and it will ask before each install." Answers: **Start the detailed
  tutorial** / **Finish here**. On **Finish here** the greeter says "Enjoy Spaced
  Linux" and hands off to the ordinary desktop.
- **Stores:** per-step completion flags and the applied-step manifest.
- **Retention:** the manifest is kept until rolled back or purged; no transcript
  of the tutorial is kept.
- **Resource ceiling:** a model larger than `qwen2.5:0.5b` may be offered only as
  an explicit row naming the model ID and its reported size, one model resident
  at a time, never switched silently; total tutorial time is capped at 30 minutes
  of instruction, with installs and downloads outside that clock but still one at
  a time.
- **Cancellation and rollback:** any step may be refused; **Undo what Voxa
  installed** removes exactly the refs in the manifest. A step that fails is
  reported and left failed.
- **No-hardware/no-audio path:** every tutorial step is pointer-driven as well;
  the tutorial is completable by a user with no microphone.

## 2. Offline and online behaviour

M0, M1, M2 and M4 work with no network at all: their speech is pre-recorded media
shipped inside the `spaced-welcome` package and their inference, where any exists,
is local. M3 and M5 are network actions by definition, and must say so: each
names the origin it will contact and the bytes it will fetch before it contacts
it. The offline determination already made by the Calamares welcome module
(`overlays/etc/calamares/modules/welcome.conf`, which checks
`https://flathub.org` and requires 5 GB of storage) is reused rather than
re-probed by a second mechanism.

Offline, or when the check fails, the greeter states that the milestone needs a
network, names what it would have downloaded and from where, stops that milestone,
and leaves every earlier milestone intact. It never substitutes a cached or
smaller artifact without saying so, never reports success for work it did not do,
and never contacts anything for telemetry, update checks or "capability" probes.
No milestone phones home.

## 3. Microphone consent and retention

Consent is asked once per milestone, in the greeter's own window, and is answered
by the user — by voice or by pointer. Nothing else answers it: not a notification,
not a log line, not a background process, not a previous run. There is no default
yes, no timeout that proceeds, and no inheritance: a yes for calibration is not a
yes for an install, for a larger model, or for a later milestone.

Capture is transient by construction. It exists only under
`$XDG_RUNTIME_DIR/spaced-welcome-capture/`, mode 600, and is unlinked when the
milestone ends — including on cancel, on crash and on power loss. What survives
are derived numbers, not audio. Nothing is uploaded, nothing is copied to a
system-wide location or another user's files, and nothing is retained by the
distribution. The greeter's diagnostic bundle carries device names and capability
flags only, consistent with the Audio row of the [subsystem map](SUBSYSTEMS.md)
and the persistence already done by `overlays/usr/local/bin/spaced-audio-restore`;
it carries no capture and no calibration numbers unless the user attaches them
deliberately. **Forget** deletes the greeter's whole record and says what it
deleted.

## 4. Model selection and resource limits

The default model is `qwen2.5:0.5b`, and it is the ceiling for M0 through M4. A
larger model may be offered only from M5, only as a plan row that names the model
ID and the download size the registry reports, and only on an explicit user
choice. One model is resident at a time; the greeter never switches, pulls or
deletes a model silently.

Ceilings: one model process, one inference request at a time, one install or
download at a time, and never a download concurrent with capture or inference.
Each spoken exchange has a 90-second wall clock with a visible timeout; M4 is
capped at 4 minutes and M5 at 30 minutes of instruction. The greeter's own state
stays under 64 KiB. Before a download it measures free space on the target and
refuses a plan that does not fit, naming both numbers.

When the model is absent, or the download failed, or the machine is offline: the
greeter says which model is missing and what it would have downloaded, falls back
to its shipped clips and on-screen text, and completes the milestone in that form.
It does not start a download to fix the absence unless the user approves that row.
A failed download leaves the previous model and the previous state intact and
offers a retry the user must choose.

## 5. Accessibility and the no-audio path

The no-audio path is not a fallback mode; it is a first-class path that always
exists. Every spoken string has the same text on screen. Every voice command —
including `voxa quit` — has a keyboard and pointer equivalent, and every consent
prompt can be answered by pointer. No milestone may require audio to finish, and
no milestone may be left in a state where the only way out is to speak.

Targets are large and pointer-selectable, starting with the issue's two-button
chooser. The progress dial shows a percentage and the same value as text. Colour
comes from the active desktop theme, as it does for every Spaced application
(see [THEME-COLORS.md](THEME-COLORS.md) and
`overlays/usr/local/bin/spaced-theme-palette`); the greeter hard-codes no colours,
so it stays readable on all thirteen metathemes. Motion is limited to the dial;
nothing flashes.

The greeter is part of Voxa and must not be mistaken for Voice2Text: different
name, different window, different voice, no shared icons, strings or launcher. A
user of Voice2Text is never offered a Voxa prompt, and the greeter never routes
input through Voice2Text.

## 6. Privileged hardware and application-install actions

No privileged helper runs without a stated reason the user can see, naming the
action, the target and the effect, before it runs. The greeter does not call a
root helper implicitly, does not reuse another application's elevation, and does
not ask for rights it has not named.

Hardware actions are read-only up to M2. Loading or building a driver, changing
an audio card profile, or altering any device setting is a plan row in M3 or later
with its own approval, and the [subsystem map](SUBSYSTEMS.md) boundary applies: a
successful VM does not validate a physical device, so a milestone may not claim
hardware support it has not measured.

Application installs follow [application delivery](APPLICATION-DELIVERY.md): first
party applications by app ID from the signed `spaced-github` remote, general
applications from Flathub, user scope for end-user applications, never a mutable
GitHub "latest release" bundle. APT installs go through the same transaction
validation the shipped updater uses, so the guard at
`overlays/usr/lib/spaced-linux/spaced-update-apt-guard` still refuses a plan that
would change the sysvinit system or remove a core Spaced package. Because an
update that replaces the login service ends a running desktop session, the greeter
never runs such a transaction silently: it warns before it starts, in line with
the rule already recorded in [FIXES.md](FIXES.md).

## 7. Cancellation and rollback

`voxa quit` is the escape the issue names, and it is honoured at every milestone,
at any moment, returning the user to the current Spaced Welcome. Every milestone
also has a visible **Stop** and a **No** answer, and a timeout never proceeds on
its own.

Work is transactional per milestone. M0-M2 and M4 change nothing, so cancelling
them is complete by definition, and any capture they held is deleted. M3 and M5
record what they applied in their own manifest; **Undo what Voxa installed**
removes exactly those refs and nothing the user installed themselves. A cancel
mid-plan stops after the current row and reports which rows completed, which were
skipped and which failed. A failure leaves the previous state intact, is reported
with its origin, and is retried only if the user chooses. The greeter never
auto-retries, never repairs a failure by installing something else, and never
describes a partial run as a success.

## 8. Service lifecycle

The greeter is a program the user starts, not a service the machine starts. It
owns its own process tree and nothing else: no daemon, no autostart entry, no
init script, no resident helper, no lock held after it exits. When it exits,
nothing of it is running and no pidfile is left behind. Any process it starts —
a model backend, a capture, a player — is its own child, started and stopped by
it, with a pidfile under `$XDG_RUNTIME_DIR/`, and it is terminated on every exit
path including crash and cancel.

Spaced Linux is sysvinit-only. If a background helper is ever needed for any
milestone, it follows the pattern this tree already ships in
`overlays/etc/init.d/spaced-first-boot-snapshot` and
`overlays/etc/init.d/spaced-wsdd`: an LSB init script with explicit runlevels,
`start|stop|restart|force-reload|status`, `start-stop-daemon` with a pidfile under
`/run`, a drop to an unprivileged user, `exit 0` when the program is absent, and
a `status` branch that reports the truth. A background child of a script that
holds a `flock` must close the lock descriptor (`7>&-`), or it keeps the lock for
its lifetime. No init-system unit or name appears anywhere in this design, and
`scripts/check.sh` fails the build if an init-system-named package other than the
two standalone utilities the image already carries enters the image set.

Lifecycle independence: the greeter's start or stop must not depend on the desktop
session, the panel, the audio subsystem or Voxa being up, and its failure must not
take any of them down. Welcome's own lifecycle stays as
[application delivery](APPLICATION-DELIVERY.md) describes it.

## 9. Ownership: Welcome, Voxa and this repository

| Milestone | Owning repository | Delivery artifact | Release that carries it |
|---|---|---|---|
| M0 opt-in chooser | `crhy/spacedwelcome` | `spaced-welcome` Debian package | next `spaced-welcome` release after the pin in `config/external-artifacts.conf` (currently `0.1.22`), staged by `scripts/iso/stage-external-artifacts.sh` |
| M1 hardware report | `crhy/spacedwelcome` | same `spaced-welcome` release | a Welcome release; read-only probes reuse what this repository already ships |
| M2 consented calibration | `crhy/spacedwelcome` for capture and consent; Voxa's own runtime in `crhy/voxa` for anything that applies the result | same `spaced-welcome` release, plus a Voxa application release | a Welcome release and a Voxa release |
| M3 approved install plan | `crhy/spacedwelcome` for the plan UI; `crhy/spacedbazaar` for the catalog rows the plan can name | `spaced-welcome` package plus the signed `spaced-github` Flatpak catalog | a Welcome release and a catalog publication |
| M4 brief training | `crhy/spacedwelcome` | same `spaced-welcome` release | a Welcome release |
| M5 long tutorial | `crhy/spacedwelcome`, with `crhy/spacedbazaar` for every application it can offer | `spaced-welcome` package plus signed Flatpak origins | a Welcome release and catalog publications |

This repository holds no copy of Welcome's or Voxa's source. What it owns is the
pin (`config/external-artifacts.conf`), the staging and verification
(`scripts/iso/stage-external-artifacts.sh`), the Calamares welcome module
configuration (`overlays/etc/calamares/modules/welcome.conf`), the display manager's seat setup
(`overlays/etc/lightdm/lightdm.conf.d/60-spaced-installed.conf`, which sets
`greeter-setup-script`),
the desktop-side helpers a milestone may reuse, and this contract. A change here
alone does not ship a Welcome fix; a change in `crhy/spacedwelcome` alone does not
reach an ISO until the pin moves and the artifact is verified.

A future pull request in `crhy/spacedwelcome` cites the milestone row of this
document it satisfies, and the review holds it to the milestone's *never* list and
to the [Never list](#the-never-list) below.

## The Never list

These are absolute. No setting, preference, plan, grant or release turns any of
them off, and each states what it costs.

1. **Never** record, keep or replay microphone data without an explicit yes to
   that milestone's consent prompt. Even after a yes, no capture is kept once the
   milestone ends. Cost: no re-usable voice profile, no later re-training from a
   stored recording.
2. **Never** install anything, Flatpak or APT, in the background, or before the
   user has approved a visible plan. This is the direct answer to the issue's
   "spaced bazaar, and libre office, audacious, vlc are installed in the background
   as flatpaks" during sound calibration: they are not. Each becomes a row in a
   plan the user has read and approved. Cost: the install no longer overlaps the
   calibration, so first boot takes longer.
3. **Never** touch another application's volume or microphone gain. The greeter
   plays at its own level and proposes values; the user applies them in that
   application's own interface or approves them as a named plan row. Cost: the
   "adjust the speakers real time" step becomes "play at these levels, you choose
   one".
4. **Never** require audio to finish. A keyboard and pointer path always exists
   for every prompt, every answer and every escape. Cost: none accepted; a
   milestone that cannot complete without audio is not shippable.
5. **Never** run a privileged helper without a stated reason the user can see,
   naming the action, the target and the effect.
6. **Never** leave a service, daemon, autostart entry, init script or lock behind,
   and never add an init-system unit or name to this design: sysvinit only.
7. **Never** contact a network service without saying so and without an approved
   plan; never telemetry, never a phone-home, never a silent fallback to a
   networked path when a local one would have worked.
8. **Never** answer a consent prompt for the user: no default yes, no timeout
   that proceeds, no consent inherited from another milestone or remembered from
   a previous run.
9. **Never** claim an install, download, calibration or hardware result that did
   not happen, and never repair a failure by doing something the user did not
   approve.
10. **Never** enable a model larger than the default without an explicit user
    choice naming the model and its size, and never switch models silently.
11. **Never** present this greeter as Voice2Text or share its interface with
    Voice2Text: the two must look nothing alike.
12. **Never** hard-code colours: the greeter takes them from the active desktop
    theme, as every Spaced application does.

## What this contract does not decide

The contract fixes the order, the consent model, the ceilings and the ownership.
It does not decide the product questions that are rhY's to make, and it does not
unlock any milestone by itself:

- which voice, character and visual design the greeter uses, and what "look a lot
  more enticing" means within the theme-colour rule;
- which nine browsers the chooser offers, and which applications each tutorial
  step may propose;
- the wording of anything beyond the consent prompts fixed above;
- whether Voxa's runtime ever gains a persistent helper, and if so which one.

Every implementation milestone remains open: it needs `crhy/spacedwelcome`, real
hardware rather than a VM, consented audio, and rhY's product choices. Until a
milestone's tested API exists, the milestone after it stays locked, and #283 stays
open.
