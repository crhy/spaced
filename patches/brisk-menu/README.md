# Brisk application context actions

The Devuan `brisk-menu` 0.6.2-2 package exposes only actions declared by an
application's desktop file. `0001-add-spaced-context-actions.patch` adds the
four distribution actions requested in issue #354 and hands the selected
desktop file to `spaced-app-action`. It also fixes the lifetime of the
`GDesktopAppInfo` stored by existing desktop actions.

`0002-support-alacarte-menu-editor.patch` also checks for Alacarte when opening
Edit Menus. Spaced installs Alacarte rather than MenuLibre or Mozo (#379).

`0003-configurable-menu-button-icon.patch` adds **Change Menu Icon** to the
panel menu context menu and a separate **Restore Default Menu Icon** action.
The chooser supports Cancel, and the per-user setting survives panel restarts
(#379). Reset lives outside the chooser because desktop file-picker portals
do not expose custom dialog buttons.

`sources.sha256` pins the Devuan source archives. Build with `make marco`, or
prepare the patched source without compiling with
`scripts/iso/build-brisk-menu.sh --prepare-only`. The package version is
`0.6.2-2+spaced10.26.8`.
