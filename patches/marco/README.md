# Marco PID namespace fixes

Spaced 9.26 backports the two upstream fixes from
[MATE Marco PR #786](https://github.com/mate-desktop/marco/pull/786) onto
Debian/Ceres `1.26.2-6`. The original upstream patches are stored unchanged.
The resulting package version is `1.26.2-6+spaced9.26.1` so an upstream
version that includes the fixes can supersede it normally.

XRes returns `Success` (zero), not a Boolean; the old inverted test discarded
the host PID and used an application's namespace PID. Its additional mask
check could also discard valid results. That made sandboxed apps appear to
belong to unrelated root processes. These changes repair PID lookup instead
of hiding the “as superuser” annotation in compiled libraries.

Source archives and Debian packaging come from
`https://mirror.hootsoftware.com/devuan/merged/pool/DEBIAN/main/m/marco/`; their SHA-256 hashes are
pinned in `sources.sha256`, using the source descriptor's archive hashes.
Build with `scripts/iso/build-marco.sh` in a disposable Debian/Devuan build
environment containing the build dependencies in the source descriptor.
The script never installs dependencies or edits the build host's packages.
Use `--prepare-only` to verify, unpack, apply patches and inspect the source.
Artifacts and the patched source stay under `build/marco` by default.

Validation still requires a test session with a sandboxed X11 application and
a real root-owned application: only the latter should retain its annotation.
Compiz's decorator and Marco's standalone window manager must both be checked.
