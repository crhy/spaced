# Compiz main plugins

Rebuild Devuan's `compiz-plugins-main` 0.8.18-8 as
`2:0.8.18-8+spaced11.26`. `sources.sha256` pins the source descriptor and
archives; the build script verifies them before extraction and applies the
tracked quilt patches. The ISO and APT repository use the same runtime package.

`0001-ezoom-consume-smooth-scroll.patch` addresses [#371](https://github.com/crhy/spaced/issues/371).
Qt receives XI2 fractional scroll events before Compiz's passive Button4/5
grab activates. ezoom now acquires a pointer grab when its configured wheel
modifier chord becomes active, with `owner_events=False`. It releases the
grab on modifier changes, binding changes and plugin shutdown. Other active
plugin grabs and additional modifiers are respected.

`0002-ezoom-wheel-grab-yields-to-other-buttons.patch` repairs the shortcut that
patch 0001 stole. The wheel grab is taken for a *modifier chord*, and Spaced
binds the same chord (Shift+Super) to Fire Writing on Button1. A grab outlives
a whole button press, and plug-ins refuse to start while another screen grab
exists (`firepaint.c`: `otherScreenGrabExist (s, NULL)`), so Shift+Super+left-drag
painted nothing while Ctrl+Alt+Shift+left-drag worked. The grab is now released
for the duration of a press on any button that is not a configured wheel button,
and is taken again when that button comes back up while the chord is still held
and no other plug-in holds a grab. Wheel suppression is unchanged; see
[the Compiz notes](../../docs/COMPIZ.md).

Build with `make marco`; stage with `scripts/iso/stage-compiz-plugins-main.sh`.
See [the manual regression probe](../../tests/manual/ezoom/README.md).
The test must check both application event suppression and visible desktop
zoom: suppressing the application alone would conceal a broken zoom action.
