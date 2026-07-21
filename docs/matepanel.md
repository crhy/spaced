# Spaced Linux 7.26 — MATE Panel Layout

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
[BriskMenu] [WindowList] ..................... [NotificationArea] [Clock] [ShowDesktop]
    ↓             ↓                            ↓                   ↓           ↓
  pos 0        pos 20                      pos 60, end         pos 66, end  pos 0, end
```

All applets are `locked=true`.

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
