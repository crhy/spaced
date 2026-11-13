# Contributing to Spaced Linux

Spaced Linux is a Devuan Ceres based desktop: sysvinit, MATE, Compiz, Caja,
Calamares, APT for the system and Flatpak for applications. Spaced Linux does
not use systemd.

## Report a bug

Open an [issue](https://github.com/crhy/spaced/issues) and include what
[README.md](README.md) asks for:

- the Spaced version (`cat /etc/os-release`);
- whether you are on a live USB or an installed system;
- the steps that reproduce the problem;
- what you expected instead;
- the output of `spaced-graphics-report` for any display problem.

The [bug report template](.github/ISSUE_TEMPLATE/bug_report.md) asks for those
fields. Security problems go through [SECURITY.md](SECURITY.md), not a public
issue.

## Build and test

```bash
make deps    # host build and test dependencies
make check   # the full source gate
python3 -m unittest discover -s tests   # the unit tests on their own
```

`make check` runs `scripts/tests/`, `scripts/check.sh`, the unit tests and the
GTK desktop test. It is the gate every change has to pass, and it needs no
network, no root and no real hardware. pytest is not installed; the tests are
plain `unittest` files named `tests/test_<name>.py`. A fix is expected to come
with a test that fails before the fix and passes after it.

`make release` runs the preflight and builds the ISO; `make iso-smoke` boots the
built ISO in KVM and VirtualBox. The start-to-finish order is in
[docs/RELEASE-CHECKLIST.md](docs/RELEASE-CHECKLIST.md).

## House rules

Taken from [AGENTS.md](AGENTS.md):

- sysvinit only. Never add a package or script that would replace the init
  system Spaced ships.
- Keep it lean, fast-booting and responsive. Implement only what is asked; no
  feature creep.
- Prefer bash scripts over inline code.
- Progressive disclosure: reference another file only when it is actually
  needed.
- Never edit a published release's `CHANGELOG.md` entry or its issue evidence.
  Record a later fix under a new revision section, and say where it is
  delivered: an APT package revision, a Welcome release, or a Bazaar Flatpak.
- Unit tests run with `python3 -m unittest discover -s tests`.

## Where the work lands

- A fix goes on its own branch, tracked by a `crhy/spaced` issue, and the batch
  ships together in the next release; see
  [docs/notes/spaced-no-prs-batch-into-release.md](docs/notes/spaced-no-prs-batch-into-release.md).
  Pull requests are still welcome: describe what changed and how it was tested.
- Welcome, Spaced Monitor and SpacedBazaar are separate repositories and this
  repository holds no copy of their source. Fix them there, then re-pin the
  release tag and archive checksum in `config/external-artifacts.conf`.
- Close an issue only after the fix is merged to `main`, and released for a
  component repository.

## Documentation

[docs/README.md](docs/README.md) indexes everything under `docs/` in three
groups: using Spaced Linux, working on it, and the per-release records. Add a
line there when you add a document. Run `make check` before committing theme or
documentation changes.

## Licence

Project-specific build configuration and code in this repository are released
under the [rhY License 1.0](LICENSE), with the GNU GPL version 3 or later as the
fallback. Contributions to this repository are accepted under that same licence.
Upstream packages, artwork, themes, fonts and components keep their own
licences.
