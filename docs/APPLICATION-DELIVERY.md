# Application delivery

Spaced Linux uses native Debian packages for desktop integration and Flatpak
repositories for end-user applications. Three independently maintained pieces
meet at the ISO boundary:

- [`crhy/spacedwelcome`](https://github.com/crhy/spacedwelcome) publishes the
  `spaced-welcome` Debian package. It owns the Welcome executable, desktop and
  autostart files, application list, and installation workflow.
- [`crhy/spacedbazaar`](https://github.com/crhy/spacedbazaar) publishes the
  `io.github.crhy.SpacedBazaar` Flatpak and the signed first-party repository.
- this repository pins those release artifacts, installs them into the image,
  and supplies the desktop-wide Flatpak source policy. It does not copy either
  application's source code.

## Runtime topology

The image registers two signed remotes:

| Name | URL | Purpose |
|---|---|---|
| `flathub` | `https://dl.flathub.org/repo/` | General applications and shared runtimes |
| `spaced-github` | `https://crhy.github.io/spacedbazaar/flatpak-repo/` | Searchable CRHY/Spaced Linux applications |

The canonical first-party descriptor is
`https://crhy.github.io/spacedbazaar/spaced-github.flatpakrepo`. It must carry
the repository's base64-encoded public GPG key. Both its file checksum and the
primary key fingerprint are pinned before an ISO can be prepared.

`spaced-github` is a real Flatpak OSTree repository, not a GitHub API search
adapter. GitHub release assets do not provide a global application catalog,
dependencies, signatures, or update graph. The publishing job imports each
approved CRHY application release into the signed repository and regenerates
its AppStream metadata. SpacedBazaar can then discover these applications with
the same libflatpak search path it uses for Flathub.

The build registers both remotes system-wide. A MATE login helper also adds
them for each user because SpacedBazaar installs optional applications into the
user Flatpak installation. Registration always uses the packaged signed
descriptors; neither path disables GPG verification.

## Boot and first-login order

1. `scripts/iso/stage-external-artifacts.sh` downloads or accepts local
   overrides for Welcome, SpacedBazaar, and the `spaced-github` descriptor.
2. Every input is SHA-256 verified. The script also checks the Debian package
   name/version/architecture, descriptor repository URL, and signing-key
   fingerprint.
3. `spaced-welcome` is placed in live-build's local Debian package directory,
   and `spaced-meta` depends on it explicitly.
4. The verified remote descriptor is incorporated into
   `spaced-mate-default-settings`, so APT upgrades retain the source policy.
5. The live-build chroot hook registers the system remotes and installs the
   pinned SpacedBazaar bundle system-wide. It verifies the application ID and
   its `spaced-github` update origin before removing the bootstrap bundle.
6. Only after the image boots does the standalone Welcome package's autostart
   entry run. SpacedBazaar is therefore present in both the live and installed
   filesystem before Welcome appears.

Calamares copies the configured live root, including `/var/lib/flatpak`, into
the target. No systemd unit is involved; the only per-user setup is a normal
MATE XDG autostart helper.

## Release pins and local development

All default coordinates live in `config/external-artifacts.conf`. Release URLs
are derived from one repository, version, tag, and architecture mapping rather
than repeated in Welcome or shell scripts. The accepted mappings are:

- Debian `amd64` to Flatpak `x86_64`;
- Debian `arm64` to Flatpak `aarch64`.

An `UNRELEASED` tag, checksum, or fingerprint is intentional: it makes
`make prepare` stop instead of silently embedding an old release. Before an ISO
release, replace every gate with published values and run `make check` plus a
clean `make prepare`.

Concurrent local development uses explicit artifact paths and their calculated
checksums:

```sh
make prepare \
  SPACED_WELCOME_DEB=/absolute/path/spaced-welcome_0.1.0_all.deb \
  SPACED_WELCOME_SHA256=<sha256> \
  SPACED_GITHUB_REMOTE_FILE=/absolute/path/spaced-github.flatpakrepo \
  SPACED_GITHUB_REMOTE_SHA256=<sha256> \
  SPACED_GITHUB_GPG_FINGERPRINT=<40-hex-fingerprint>
```

The same version, tag, and URL variables may be overridden for a release
candidate. A local path never bypasses checksum, package metadata, or signing
key verification.

## Publishing and update contract

For every CRHY Flatpak release:

1. build and test both supported architectures where the application supports
   them;
2. export the signed ref into the central `spaced-github` repository;
3. regenerate signed summary, static deltas, and AppStream metadata;
4. publish the repository atomically;
5. publish bundles made with `flatpak build-bundle --repo-url` pointing to the
   central repository, so bundle installs retain an update origin;
6. verify search, install, launch, and update from a clean user installation.

Welcome should install first-party applications by app ID from
`spaced-github`, not by resolving a mutable GitHub “latest release” bundle.
Its task-oriented Help & Apps page launches exact `appstream://` locations in
the post-install SpacedBazaar, while Bazaar's curated view surfaces the same
Create, Work, and Play recommendations from Flathub.
SpacedBazaar itself is pinned for ISO reproducibility, then receives subsequent
versions from its configured Flatpak origin. The standalone Welcome package is
updated through the Spaced APT repository and the `spaced-meta` dependency.

## Required release tests

- Run `make check` and validate every YAML, JSON, shell, Python, and desktop
  file.
- Run `make prepare` with released pins; no override or `UNRELEASED` value may
  be necessary.
- In the chroot, verify both system remotes, the SpacedBazaar app ID, and its
  `spaced-github` origin.
- Boot the live ISO offline and confirm SpacedBazaar launches before any
  first-login downloads.
- Boot online and confirm both user remotes appear after login.
- Search for and install Voice2Text, Scum with Cats, Brutal Chess, and Spaced
  Update from SpacedBazaar and from standalone Welcome.
- Open each Welcome Help & Apps choice and confirm SpacedBazaar navigates to
  the exact suggested application without starting an installation.
- Publish a newer test commit to a staging repository and confirm `flatpak
  update` upgrades an existing app without downloading a GitHub bundle.
