# Caja fixes

`0003-fix-overflowing-desktop-icon-position.patch` backports upstream commit
[`333e272`](https://github.com/mate-desktop/caja/commit/333e2728dbebb12110fc9b2c821089eb372ee14e).
Caja now loads an icon's image and label dimensions before assigning its
desktop position, so newly mounted Gigolo volumes that would cross the bottom
edge are wrapped instead of being clamped behind the panel (Spaced issue #389).

`0002-persist-show-hidden-files.patch` makes the View menu and Ctrl+H update
the existing `show-hidden-files` preference. New windows and restarted Caja
processes retain the selection (Spaced issue #379).

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
`1.26.4-3+spaced11.26`.

The ISO and APT builders stage Caja, caja-common, libcaja-extension1 and
gir1.2-caja-2.0 together. The APT builder also includes the corresponding
source package. Remove this backport when the distribution package includes
the upstream fix.
