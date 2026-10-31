# Compiz main plugins

Rebuild Devuan's `compiz-plugins-main` 0.8.18-8 as
`2:0.8.18-8+spaced10.26.8`. `sources.sha256` pins the source descriptor and
archives; the build script verifies them before extraction and applies the
tracked quilt patch. The ISO and APT repository use the same runtime package.

`0001-ezoom-consume-smooth-scroll.patch` addresses [#371](https://github.com/crhy/spaced/issues/371).
Qt receives XI2 fractional scroll events before Compiz's passive Button4/5
grab activates. ezoom now acquires a pointer grab when its configured wheel
modifier chord becomes active, with `owner_events=False`. It releases the
grab on modifier changes, binding changes and plugin shutdown. Other active
plugin grabs and additional modifiers are respected.

Build with `make marco`; stage with `scripts/iso/stage-compiz-plugins-main.sh`.
See [the manual regression probe](../../tests/manual/ezoom/README.md).
The test must check both application event suppression and visible desktop
zoom: suppressing the application alone would conceal a broken zoom action.
