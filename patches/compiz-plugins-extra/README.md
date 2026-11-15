# Compiz extra plug-ins

Rebuild Devuan's `compiz-plugins-extra` `2:0.8.18-5` as
`2:0.8.18-5+spaced11.26.2`. `sources.sha256` pins the source descriptor and
archives; the build script verifies them before extraction and applies the
tracked quilt patches. The ISO and the APT repository use the same runtime
package.

`0001-firepaint-yields-grab-to-key-shortcuts.patch` lets Fire Writing step
aside for a keyboard shortcut. Fire Writing holds a Compiz screen grab for
the whole stroke (`firepaint.c: pushScreenGrab (s, None, "firepaint")`), and
Compiz turns that into an X pointer and keyboard grab on its grab window
(`src/screen.c: pushScreenGrab`). The X server keeps one grab at a time, so
while a stroke is in progress another client's `XGrabPointer`/`XGrabKeyboard`
returns `GrabAlreadyGrabbed`. `mate-screenshot --area` selects its area with
exactly such a grab, so Shift+Print produced no image at all. The grab is
released for a key press and key release and taken again on the next button
press; the fire already on screen is untouched. See
[the Compiz notes](../../docs/COMPIZ.md).

Build with `make marco`; stage with
`scripts/iso/stage-compiz-plugins-extra.sh`. A core change also needs the
ABI and plug-in compatibility check against this package, and vice versa:
`checkPluginABI ("core", CORE_ABIVERSION)` is the only gate.
