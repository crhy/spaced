# Compiz decorator: title-bar button click areas

Spaced 10.26.2 rebuilds Debian/Ceres `compiz 2:0.8.18-9` as
`2:0.8.18-9+spaced10.26.2` with one change to `gtk-window-decorator`
(issue [#279](https://github.com/crhy/spaced/issues/279)).

With a Marco theme the decorator "compensated" for Marco's invisible resize
border by moving the click area of every right-hand title-bar button left by
that border (10 px) and **down** by it. The geometry libmarco returns already
includes the border, so the result was a click area displaced from the drawn
button: measured with `scripts/tests/titlebar-hit-test.sh`, only 15 px of the
28 px title bar responded (18 px once the theme boxes were enlarged), and the
area sat about 10 px left of the icon. The patch removes the compensation.

Source archives and Debian packaging come from
`https://mirror.hootsoftware.com/devuan/merged/pool/DEBIAN/main/c/compiz/`;
their SHA-256 hashes are pinned in `sources.sha256`. Build with
`scripts/iso/build-compiz.sh` inside the same disposable chroot as Marco
(`make marco` runs both). `--prepare-only` verifies, unpacks, applies the
patch and stops. Artifacts stay under `build/compiz`.

Because the Compiz binary packages depend on each other by exact version,
all of `compiz`, `compiz-core`, `compiz-gnome`, `compiz-mate`,
`compiz-plugins` and `libdecoration0t64` are shipped from this build.

Validation: `scripts/tests/titlebar-hit-test.sh` in a session using the
rebuilt decorator must report each button's click area as tall as the button
box and ending within a few pixels of the window's right edge.
