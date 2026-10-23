# Caja cross-filesystem move fix

Caja 1.26.4-3 loses the destination selected in the conflict dialog when a
move falls back to copying and deleting across filesystems. The user can be
asked to resolve the original conflict a second time.

`0001-preserve-move-rename.patch` backports the merged upstream change from
[MATE Caja PR #1888](https://github.com/mate-desktop/caja/pull/1888).
It retains the selected destination through the fallback and releases its
reference when the operation completes. This does not claim to fix unrelated
copy cancellation hangs or SMB performance reports.

`sources.sha256` pins the Devuan/Debian 1.26.4-3 source archives. Build with
`make marco`; `scripts/iso/build-caja.sh --prepare-only` can also prepare the
patched source without compiling. The package version is
`1.26.4-3+spaced10.26.6`.

The ISO and APT builders stage Caja, caja-common, libcaja-extension1 and
gir1.2-caja-2.0 together. The APT builder also includes the corresponding
source package. Remove this backport when the distribution package includes
the upstream fix.
