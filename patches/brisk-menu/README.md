# Brisk application context actions

The Devuan `brisk-menu` 0.6.2-2 package exposes only actions declared by an
application's desktop file. `0001-add-spaced-context-actions.patch` adds the
four distribution actions requested in issue #354 and hands the selected
desktop file to `spaced-app-action`. It also fixes the lifetime of the
`GDesktopAppInfo` stored by existing desktop actions.

`sources.sha256` pins the Devuan source archives. Build with `make marco`, or
prepare the patched source without compiling with
`scripts/iso/build-brisk-menu.sh --prepare-only`. The package version is
`0.6.2-2+spaced10.26.7`.
