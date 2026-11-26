# Peer-to-peer repository transport: design only

Status: design document for [crhy/spaced#9](https://github.com/crhy/spaced/issues/9)
("New torrent based repos. With blockchain verification."). **Nothing described in
this file is implemented.** There is no client code, no configuration key, no
published torrent, no init script, no scheduled job and no user-facing setting in
any Spaced repository. Every sentence below is a requirement a later implementation
must satisfy, not a description of behaviour Spaced Linux has today. The delivery
contract that actually ships is [APPLICATION-DELIVERY.md](APPLICATION-DELIVERY.md);
this document only proposes a transport that may sit in front of it.

## Why this document exists

`docs/11.26.1-RELEASE-REVIEW.md` keeps Spaced #9 open as
"Long-term distribution infrastructure, signing and availability design | Define
signed metadata, seeding, mirrors and fallback behavior." The issue's own comments
already phase the work — P2P transport of signed bytes first, then a signed snapshot
manifest anchored periodically, then a full repository clone — and name this file as
the first deliverable. So this document is the deliverable: it fixes the vocabulary,
the trust roots and the threat model, so a later phase can be implemented and tested
against something written down rather than argued from memory. The overlapping issue
#51 is closed; #9 stays open for the implementation phases.

## What ships today

| Trust root | Where it lives | What it proves |
|---|---|---|
| APT archive key | `overlays/usr/share/keyrings/spaced-archive-keyring.gpg`, with the fingerprint pinned in `scripts/build-apt-repo.sh` and `scripts/publish-apt-package.sh` | The `crhy/spaced-apt` index came from the Spaced key, and it is only valid for `SPACED_APT_VALID_DAYS` (180 days by default), so a frozen or replayed copy stops being installable |
| Flatpak repository keys | the two signed remotes registered system-wide, plus the pinned `spaced-github` descriptor and its primary-key fingerprint in `config/external-artifacts.conf` | The OSTree refs and AppStream metadata came from Flathub or from `crhy/spacedbazaar`; neither registration path disables GPG verification |
| Artifact digests | `scripts/iso/stage-external-artifacts.sh`, and the ISO's published `.sha256` | The bytes that entered the image, and the bytes a user downloaded, are the bytes the release published |

A peer-to-peer layer may supply bytes to these checks. It may not stand in place of
them.

## Threat model

Name the adversary before choosing the mechanism. The parties, in the order the
phases have to handle them:

| Adversary or failure | What they can do | What must stop them |
|---|---|---|
| Hostile or buggy peer | Serve altered, truncated, or unrelated bytes; serve a package index of its own choosing; serve content under a name you never requested | Per-chunk and whole-file SHA-256 against the value origin publishes; signature verification against the shipped keyring; peer-supplied metadata treated as an unauthenticated hint only |
| Stale or replayed snapshot | Keep an old, still-signed index alive after origin has moved on, or replay an index that was valid once | `Valid-Until` on the APT index, the anchor's sequence number, and comparison against origin's current index; a stale snapshot is a fallback, never the default |
| Downgrade attempt | Replace an installed component with an older signed one | Refuse an implicit downgrade; an older revision may only be installed because the user asked for it, and it must still verify |
| Key compromise or misuse | Sign bytes the project would not have published | Out of scope for P2P: only origin's key ceremony and keyring rotation can address it. Say so rather than implying a transport layer helps |
| Origin outage or throttling | Make updates unavailable (GitHub Pages limits, network loss) | Deterministic fallback to origin, then to a verified peer, with the transport recorded; never invent a missing expected value |
| Privacy observer | Learn which packages or ISOs a machine downloads, and correlate them with the machine | Seeding opt-in, no public DHT or tracker for OS content by default, per-user cache, no disclosure of local state to peers |
| Bandwidth abuser | Make one client upload without bound, or exhaust the 1 GB Pages budget that `crhy/spaced-apt` shares | Per-client upload cap, bounded seed lifetime, chunk reuse, retention policy kept separate from the anchor log |

Explicit non-goals: this design does not authenticate content (the signing key does
that), does not protect against a malicious or compromised origin, does not hide what
you downloaded from a peer already talking to you, and does not make an update
available when no origin and no anchor is reachable.

## Trust model (invariants)

1. APT GPG signature verification and Flatpak/OSTree verification stay mandatory.
   A P2P layer never replaces them. In this design that is absolute: an implementation
   that installs a package whose signature was not checked against the shipped keyring
   is wrong, whatever else it achieves.
2. A peer supplies bytes only. The expected digest and the expected identity always
   come from origin, never from the peer that happens to be available.
3. Order of operations per artifact: obtain bytes, compare SHA-256 with the value
   origin publishes, verify the signature against the shipped keyring, then hand the
   artifact to `apt`/`dpkg` or `flatpak`, which verify again in their own way. A
   transport-level check never substitutes for the package manager's check.
4. A peer never supplies a trust anchor: not a key, not a fingerprint, not a
   `.flatpakrepo` descriptor, not an `InRelease`, not a policy decision, not a
   "this digest is correct" assertion.
5. Availability is not trust. A peer being reachable, or many peers agreeing, adds
   no authority to a value origin has not published.
6. Nothing here is user-facing yet. When a control is eventually added, a "Never"
   option in it must mean never — never seed, never contact a peer, never accept a
   peer-supplied index — including where honouring it costs convenience, in line with
   [docs/notes/spaced-never-means-never.md](notes/spaced-never-means-never.md).

## What "blockchain verification" means here

Precise definition, so the phrase stops carrying promise it cannot keep:

- A **snapshot** is the signed set of metadata plus the package and ref list it names
  at one moment: an APT `InRelease` plus its `Packages` digests, or an OSTree
  repository commit plus its AppStream metadata.
- Each snapshot gets a **manifest**: a sorted list of `(path, size, sha256, signer
  fingerprint)`. The manifest's **merkle root** is a single SHA-256 computed over that
  list, the way the chunk tree below is computed over chunks.
- The **log** is append-only. Entry *n* records the snapshot id, its merkle root, the
  signer fingerprint, and the merkle root of entry *n-1*. That hash chain is the
  "blockchain" part: no earlier entry can be changed or removed without breaking every
  later entry.
- The log is **anchored periodically**: origin publishes it (and a short signed
  statement of its head) on the normal signed channels, roughly on the same monthly
  cadence `scripts/build-apt-repo.sh` already republishes the APT index.
- A client verifies chain continuity back to the last anchor it saw, verifies the
  signature on the entry it wants, and only then trusts a peer-supplied index.

What this buys:

- tamper-evidence for the *set* of valid snapshots, not just for one file;
- detection of a substituted, forked or rolled-back history, which a per-file
  signature cannot see;
- an auditable ordering of snapshots, so "which index is newer" is decidable without
  trusting the peer that supplied it;
- a transparency log a maintainer can publish cheaply, since a merkle root is a few
  dozen bytes.

What it does not buy:

- **content authentication**: the signing key already provides that for any single
  artifact; a merkle root over signed metadata adds no new authority;
- **protection against a bad origin**: origin anchoring a snapshot of packages it
  should not have published is still origin's mistake;
- **revocation**: a revoked key can still sign a well-formed chain entry, so
  revocation needs the tombstone and keyring work described below, not a chain;
- **availability**: the chain still needs at least one reachable anchor;
- **freshness**: `Valid-Until` still does that job, and a chain entry with an
  expired index must still be refused;
- **privacy**: a chain says nothing about who fetched what.

So: signed, content-addressed manifests plus a transparency log are the useful core;
the chain adds history integrity. Any claim that "blockchain verification" makes
repositories safer on its own is not supported by this design.

## Content-addressed chunking

- Split each artifact into fixed-size chunks (start at 1 MiB; measure before tuning)
  and store a SHA-256 per chunk. The torrent's own info hash is not the check: the
  chunk digests come from origin's manifest.
- Verify each chunk on write, before it is committed to the cache, and verify the
  whole-file SHA-256 against the value origin publishes before the artifact is handed
  to a package manager. A file whose chunks all match but whose whole-file digest
  does not is a bug in the manifest, and must be refused.
- Key the cache by digest, not by filename, so a name collision cannot alias two
  different artifacts and a re-fetched artifact is a cache hit rather than a write.
- Commit atomically: write to a temporary path, fsync, rename. Guard the cache with
  `flock`, and close the lock descriptor in any background child, per the standing
  rule in `AGENTS.md`.
- Reuse the existing precedent rather than inventing a new one:
  `scripts/iso/stage-external-artifacts.sh` already refuses to stage bytes whose
  SHA-256, package metadata or key fingerprint do not match the pins in
  `config/external-artifacts.conf`.

## Key rotation and revocation

Rotation:

- The signing identity is pinned in three places today: the shipped keyring, the
  fingerprint in `config/external-artifacts.conf`, and the `SIGNING_KEY` default in
  `scripts/build-apt-repo.sh` and `scripts/publish-apt-package.sh`. A rotation has to
  land in the image before any client can accept a new signature, so a rotation
  ships as an OS change, not as a repository change.
- Keep an overlap window in which both the old and the new fingerprint are accepted,
  bounded by an explicit date, and end it by removing the old key from the keyring.
  Never accept an unknown fingerprint because a peer presents it.
- Record the signer fingerprint in every log entry, so a client can tell a rotation
  from a fork, and can tell that a snapshot it holds was signed by a key that has
  since been retired.

Revocation, which is the hard part of phase 3:

- Removing a key from the keyring stops new trust; it does not delete bytes peers
  already hold. A peer pool keeps retracted content available indefinitely, so
  retraction has to be a policy the client applies, not a hope that the network
  forgets.
- A retraction therefore needs an explicit tombstone entry in the log: this snapshot
  or this ref is no longer installable, effective from this date. Clients that cannot
  reach the log must not treat "no evidence it is revoked" as "not revoked" when the
  last anchor they hold is older than the effective date.
- Retention and anchoring conflict and must be decided separately.
  `scripts/prune-apt-repo.sh` deletes superseded revisions to stay inside the 1 GB
  Pages budget, while an anchored log names snapshots that must stay resolvable.
  Decide per snapshot class what stays addressable, and keep the pruner's existing
  refusal to run on a dirty checkout or a repository without `dists/`.

## Hostile peers, replay and stale snapshots

- Treat every peer-supplied index as an unauthenticated hint. It may choose which
  artifacts to offer; it may not add a package name, version, ref or digest that
  origin's pinned manifest does not contain.
- Never execute, source or import anything a peer supplied: no hook, no script, no
  metadata file that a package manager would act on. Only `.deb`, `.tar`, OSTree
  objects and ISO bytes that have already verified may be read.
- Bound each peer's contribution: maximum share of chunks for one artifact,
  maximum total bytes accepted, and a per-peer refusal to serve a name outside the
  allow-list.
- Replay and stale handling: refuse a snapshot whose log sequence number is lower
  than the last verified one unless the user explicitly asked for that older
  revision; compare the peer's index against origin's current `InRelease` and
  `Valid-Until`; treat a stale snapshot as a fallback that is announced as stale.
- Do not let a peer's success change an expected digest, a key fingerprint or a
  snapshot id. A mismatch is a refusal, with the mismatch recorded, not a retry.
- Partial and interleaved state: a chunk that fails verification is discarded, not
  truncated into the cache; an interrupted fetch leaves no artifact a package
  manager can pick up.

## Deterministic origin fallback

Resolution order, fixed and testable:

1. origin, using the URLs already in the shipped APT and Flatpak configuration;
2. a verified peer, only when origin failed, and only against the digest origin
   publishes;
3. give up with a clear message.

- Record which transport supplied each artifact, and say so in the update output, so
  a later report can distinguish "origin served this" from "a peer served this and
  it verified".
- Peers are never added as mirrors to APT or Flatpak configuration. The shipped
  source policy stays the only source list.
- If origin publishes no expected digest for an artifact, there is no fallback: the
  client refuses rather than accepting a peer's self-declared value.
- Fallback must be deterministic in tests: same origin state, same peer state, same
  outcome, no dependence on peer arrival order.

## Rollback

- APT: rollback means installing an older published revision, which must still verify
  and must still be present. `scripts/build-apt-repo.sh` already refuses to replace
  published bytes under a version that exists, so an older revision is a different
  version (`11.26.1-2` versus `11.26.1-1`), never the same version with new bytes.
  An older revision whose index has passed `Valid-Until` must be refused with an
  explanation, not silently accepted; that is the cost of the expiry rule and it
  applies to rollback as much as to update.
- Flatpak: rollback means an earlier signed OSTree commit that is still present in
  the repository, reached through the configured origin, not through a bundle or a
  peer-supplied ref.
- A P2P layer must not add a second transaction state. Installation remains apt/dpkg
  and flatpak's business; the transport's only promise is that the bytes it hands over
  verified.

## Cache eviction, bandwidth and privacy

- Cache location: per user, under the user's own tree, so a peer cannot read another
  user's cache and a theme or session change cannot disturb it.
- Eviction: LRU by last access, with a hard size cap; never evict an artifact whose
  digest is pinned by the current snapshot or by an exact dependency pin, mirroring
  the retention logic already in `scripts/prune-apt-repo.sh`.
- Seeding is opt-in and off by default. A client must not upload to peers merely
  because it downloaded something.
- Bandwidth controls: bounded uploads per client, bounded seed lifetime, chunk reuse
  across artifacts, and a total budget that respects the 1 GB limit `crhy/spaced-apt`
  already lives under.
- Privacy controls: no public DHT or open tracker for OS content by default; an
  allow-listed peer set instead; no disclosure of installed applications, versions or
  machine state to peers; per-user cache so one user's downloads are not visible to
  another.
- Scheduling: any periodic anchor refresh or cache sweep runs from a sysvinit script
  under `/etc/init.d` plus `cron`/`anacron`. `anacron` is already installed
  (`config/packages.yaml`) so daily jobs also run on machines that are off at the
  fixed `cron` time. No always-on background process: Spaced stays lean and fast-booting,
  and nothing here may add boot-time work.

## Phased plan

| Phase | Deliverable | Proven by | Risk that must be solved first |
|---|---|---|---|
| 0 (this document) | Vocabulary, trust roots, threat model, invariants | `bash scripts/check.sh` still passes; no code changes | none |
| 1 | P2P distribution of the ISO and large blobs: publish a torrent and its detached signature beside the existing ISO and its `.sha256`; no client change, no repository change | a test that a torrent's file list and chunk digests match the published ISO, and that a tampered torrent is refused | none beyond publishing extra files; verification stays exactly as it is today |
| 2 | Signed snapshot manifest plus the anchored log described above; clients verify chain continuity and the entry signature before trusting a peer-supplied index | tests for chain continuity, fork detection, expired-index refusal, and stale-snapshot fallback | anchor publication cadence, key rotation records, retention versus addressability |
| 3 | Full repository clone or replacement, including the "replace Devuan/Flathub repos" ambition | a hostile-peer suite: substituted index, replayed snapshot, revoked key, partial fetch, deterministic fallback | revocation, key rotation, byzantine-fault tolerance, and the privacy and bandwidth controls above; treat as a separate project |

Phase 1 is the only phase that can be done without new client code, and it is the
only one whose benefit is measurable today: it moves bulk bytes off origin while
leaving every check untouched. Phases 2 and 3 are not planned for any 11.26.x
release, and phase 3 is not planned at all until the open questions below have
written answers.

## Open questions rhY must still answer

1. Is phase 1 acceptable as ISO and blob distribution only, with no OS repository
   traffic at all, and for how long?
2. Which transport implementation ships, if any, and who maintains it: a packaged
   dependency, a script in this repository, or nothing at all for phase 1?
3. Where the anchor is published so that a client can reach it over a channel that
   is not the one being verified, and what happens when that channel is unreachable.
4. Anchor cadence: monthly with the APT republish, or on every snapshot, and how
   long a client may hold an old anchor before it must refuse.
5. Retention: which snapshots stay addressable for the log, and how that reconciles
   with `scripts/prune-apt-repo.sh` and the 1 GB Pages budget.
6. Key rotation policy: overlap window length, who performs it, and how a rotation
   reaches installed systems before new signatures appear.
7. Revocation semantics: tombstones, effective dates, and what an offline client does
   when it cannot prove a snapshot is not revoked.
8. Peer discovery: allow-listed peers, or nothing public; whether DHT is ever enabled.
9. The exact user-facing controls, their defaults, and whether "Never" is one of
   them (if it is, it must be absolute).
10. Whether Flathub content may be re-seeded at all, given redistribution terms, or
    whether peers only ever carry first-party Spaced bytes.
11. How much of this belongs in `spaced-update` (`overlays/usr/lib/spaced-linux/`)
    and how much in `crhy/spacedbazaar`, and which repository owns the cache.
12. What the bandwidth and storage cost is on a modest machine, measured, before any
    of this is offered to users.

## Testing and gate expectations

- This document changes no code, configuration, packaging or ISO content. `bash
  scripts/check.sh` must still print `All source checks passed.` afterwards.
- Per [docs/ROADMAP.md](ROADMAP.md) "How to use this list": one GitHub issue per
  item, with the issue number in the row, fixes proven by `make check` and by a test
  that fails without the change. #9 is that issue for this area; it stays open until
  the phases it covers are implemented, not when this document lands.
- Spaced Linux runs sysvinit only. Design the scheduling, daemon and service parts in
  sysvinit terms — `/etc/init.d` scripts, `cron`, `anacron`, elogind — and do not
  name an alternative init system in this file or in any implementation of it.
- Do not describe behaviour the repository does not have. Where this document says a
  check must happen, the implementation needs a test that fails without it.

## Related documents

- [APPLICATION-DELIVERY.md](APPLICATION-DELIVERY.md) — the delivery contract this
  transport would sit in front of.
- [SUBSYSTEMS.md](SUBSYSTEMS.md) — ownership map; OS updates are
  `overlays/usr/lib/spaced-linux/`, not the separate `crhy/spacedupdate` tree.
- [ROADMAP.md](ROADMAP.md) — how findings turn into issues and releases.
- [notes/spaced-never-means-never.md](notes/spaced-never-means-never.md) — the
  standing rule behind invariant 6; the sysvinit-only rule is stated in
  [AGENTS.md](../AGENTS.md) and repeated under "Testing and gate expectations".
