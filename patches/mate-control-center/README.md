# MATE custom keyboard shortcut targets

The application chooser in MATE Control Center 1.28.1 stores an executable
name, losing the desktop entry's complete launch semantics. The source patch
stores `gtk-launch <desktop-id>` and adds a separate file chooser that creates
a safely quoted `spaced-open-target <path>` command. This makes applications,
executable scripts, shebang scripts, and ordinary files usable as shortcut
targets for issue #351.

The Devuan build also backports upstream commit `b5f6b8cf`, which fixes the
automatic systemd probe. When `libsystemd` is absent, the optional integration
is disabled cleanly; an explicit `--enable-systemd` still requires the library.
This keeps the package init-neutral without changing the upstream default.

`sources.sha256` pins the Devuan source archives. Build with `make marco`, or
prepare the patched source without compiling with
`scripts/iso/build-mate-control-center.sh --prepare-only`. The package version
is `1.28.1-1+spaced10.26.7`.
