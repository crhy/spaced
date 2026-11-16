# Compiz decorator fixes

See [Compiz architecture and upstream strategy](../../docs/COMPIZ.md) for
the rendering/lifetime model, internal Marco fallback, diagnostic commands,
verification matrix and recommendation to submit these as independent
upstream fixes after rebasing and validation. All four patches remain downstream;
this documentation does not claim an upstream submission.

Spaced 10.26.7 rebuilds Debian/Ceres `compiz 2:0.8.18-9` as
`2:0.8.18-9+spaced10.26.7`. It retains the title-bar button fix first
shipped in 10.26.2 (issue [#279](https://github.com/crhy/spaced/issues/279))
and protects decoration pixmaps during theme changes. It also gives Compiz
screenshots sortable date-and-time filenames (issue
[#362](https://github.com/crhy/spaced/issues/362)) and lets a screenshot
selection start while fire painting holds its screen grab.

With a Marco theme the decorator "compensated" for Marco's invisible resize
border by moving the click area of every right-hand title-bar button left by
that border (10 px) and **down** by it. The geometry libmarco returns already
includes the border, so the result was a click area displaced from the drawn
button: measured with `scripts/tests/titlebar-hit-test.sh`, only 15 px of the
28 px title bar responded (18 px once the theme boxes were enlarged), and the
area sat about 10 px left of the icon. The patch removes the compensation.

The second patch holds the X server grab from the decoration pixmap geometry
query through creation of its GLX and Damage references. Otherwise the
decorator can free the pixmap between those requests, making
`glXCreatePixmap` fail and Compiz launch Marco. A diagnostic build reproduced
that failure from `decorGetTexture` during a Windows 7 theme switch in
VirtualBox. Release testing exercises all 13 themes repeatedly. Remove this
patch when upstream provides equivalent protection for this lifetime race.

The third patch replaces Compiz's directory-dependent `screenshot1.png`
sequence with `screenshot-YYYY-MM-DD_HH-MM-SS.png`; captures made in the same
second receive `-2`, `-3`, and so on instead of replacing an existing file.

The fourth patch is about grabs, not filenames. `shotInitiate` in
`plugins/screenshot.c` refused to start whenever any plug-in other than
`screenshot` already held a screen grab, and fire painting holds one for the
whole stroke (`pushScreenGrab (s, None, "firepaint")`), so Ctrl + Shift +
left drag did nothing at all while fire was being drawn. The core already
nests a second screen grab onto a held one (`XChangeActivePointerGrab`) and
restores the outer grab when the selection ends, and firepaint only adds
points and paints particles, so the refusal now accepts a `firepaint` grab.
The capture is a `glReadPixels` taken after the whole paint chain, and Compiz
renders into the root window, so the fire is inside the saved image.

Source archives and Debian packaging come from
`https://mirror.hootsoftware.com/devuan/merged/pool/DEBIAN/main/c/compiz/`;
their SHA-256 hashes are pinned in `sources.sha256`. Build with
`scripts/iso/build-compiz.sh` inside the same disposable chroot as Marco
(`make marco` runs both). `--prepare-only` verifies, unpacks, applies the
patches and stops. Artifacts stay under `build/compiz`.

Because the Compiz binary packages depend on each other by exact version,
all of `compiz`, `compiz-core`, `compiz-gnome`, `compiz-mate`,
`compiz-plugins` and `libdecoration0t64` are shipped from this build.

Validation: `scripts/tests/titlebar-hit-test.sh` in a session using the
rebuilt decorator must report each button's click area as tall as the button
box and ending within a few pixels of the window's right edge.
