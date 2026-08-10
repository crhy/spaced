# Spaced Linux 8.26.3 — MATE Panel Layout

## Layout File

Stored at `/usr/share/mate-panel/layouts/spaced-linux.layout` (also in `mate-tweak` and gschema override as `default-layout='spaced-linux'`):

```ini
[Toplevel bottom]
expand=true
orientation=bottom
size=30
auto-hide=false

[Object brisk-menu]
object-type=applet
applet-iid=BriskMenuFactory::BriskMenu
toplevel-id=bottom
position=0
locked=true

[Object window-list]
object-type=applet
applet-iid=WnckletFactory::WindowListApplet
toplevel-id=bottom
position=20
locked=true

[Object notification-area]
object-type=applet
applet-iid=NotificationAreaAppletFactory::NotificationArea
toplevel-id=bottom
position=60
relative-to-edge=end
locked=true

[Object volume-control-applet]
object-type=applet
applet-iid=GvcAppletFactory::GvcApplet
toplevel-id=bottom
position=63
relative-to-edge=end
locked=true

[Object clock]
object-type=applet
applet-iid=ClockAppletFactory::ClockApplet
toplevel-id=bottom
position=66
relative-to-edge=end
locked=true

[Object show-desktop]
object-type=applet
applet-iid=WnckletFactory::ShowDesktopApplet
toplevel-id=bottom
position=0
relative-to-edge=end
locked=true
```

## Layout Structure

```
[BriskMenu] [WindowList] ........ [Volume] [NotificationArea] [Clock] [ShowDesktop]
    ↓             ↓                  ↓           ↓             ↓         ↓
  pos 0        pos 20            pos 63,end  pos 60,end    pos 66,end  pos 0,end
```

All applets are `locked=true`.

## One panel for every theme

Every one of the nine themed layouts (`spaced-linux`, `spaced-macos`,
`spaced-android`, `spaced-win311`, `spaced-winxp`, `spaced-mint`,
`spaced-win11-light`, `spaced-win11-dark`, `spaced-geoworks`) uses the exact
same applet composition above. The files differ only in the toplevel's
`orientation` line. Switching themes therefore never adds, removes, or
rearranges applets — the panel keeps `[BriskMenu] [WindowList] … [Volume]
[NotificationArea] [Clock] [ShowDesktop]` no matter which theme is selected.

## Panel position and docks per theme

| Theme               | Panel position | cairo-dock |
|---------------------|----------------|------------|
| Spaced Linux Dark   | bottom         | off        |
| Spaced Linux Light  | bottom         | off        |
| Mac OS X            | **top**        | **on**     |
| Windows 3.11        | bottom         | off        |
| Windows XP          | bottom         | off        |
| Linux Mint          | bottom         | off        |
| Windows 11 Light    | bottom         | off        |
| Windows 11 Dark     | bottom         | off        |
| GeoWorks            | bottom         | off        |
| Android             | **top**        | **on**     |

Android and Mac OS X move the single panel to the top edge and enable the
cairo-dock at the bottom edge; every other theme keeps the panel at the
bottom with the dock off. `panel_position` and `cairo_dock` in
`/usr/share/spaced-themes/themes.json` drive this via `spaced-switch-theme`,
which moves/resizes the existing panel in place and never restarts mate-panel
(see `docs/FIXES.md`).

## Clock Preferences

Set via dconf at `/org/mate/panel/objects/clock/prefs/`:

| Key               | Value        |
|-------------------|-------------|
| `format`          | `12-hour`   |
| `show-date`       | `false`     |
| `temperature-unit` | `Fahrenheit` |
| `speed-unit`      | `mph`       |

## Default gschema override

Stored at `/usr/share/glib-2.0/schemas/90_spaced-linux.gschema.override`:

```ini
[org.mate.panel]
default-layout = 'spaced-linux'
```

## DConf System Defaults

Stored at `/etc/dconf/db/local.d/01-spaced` and `02-panel`.
