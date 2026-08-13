# Spaced Linux MATE panel layout

This document describes the panel implementation at commit `f462bdb4b4d3916caf1617159056f2743b016acf`.

For the complete theme runtime, see [MATE-theming.md](MATE-theming.md). For panel colors, see [THEME-COLORS.md](THEME-COLORS.md#panel-colors).

## One applet composition

Every selectable Spaced theme uses the same applet composition:

```text
[Brisk Menu] [Window List] ........ [Volume] [Notification Area] [Clock] [Show Desktop]
```

The canonical bottom layout contains:

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

All objects are locked. Theme changes do not add, remove, or reorder applets.

## Layout files

Nine layout files serve ten selectable themes:

```text
spaced-linux.layout
spaced-macos.layout
spaced-android.layout
spaced-win311.layout
spaced-winxp.layout
spaced-mint.layout
spaced-win11-light.layout
spaced-win11-dark.layout
spaced-geoworks.layout
```

Linux Dark and Linux Light both use `spaced-linux.layout`. The files are otherwise intentionally almost identical; macOS and Android start with a top-oriented toplevel, while the others start at the bottom.

The layouts establish a new profile. Normal theme switching does not reload or replace the layout. Instead, `spaced-switch-theme` moves and resizes the existing panel.

## Theme mapping

| Theme | Layout | Runtime edge | Size | Cairo Dock |
|---|---|---|---|---|
| Spaced Linux Dark | `spaced-linux` | bottom | 30 | off |
| Spaced Linux Light | `spaced-linux` | bottom | 30 | off |
| macOS | `spaced-macos` | top | 30 | on |
| Windows 3.11 | `spaced-win311` | bottom | 30 | off |
| Windows XP | `spaced-winxp` | bottom | 30 | off |
| Linux Mint | `spaced-mint` | bottom | 30 | off |
| Windows 11 Light | `spaced-win11-light` | bottom | 30 | off |
| Windows 11 Dark | `spaced-win11-dark` | bottom | 30 | off |
| GeoWorks | `spaced-geoworks` | bottom | 30 | off |
| Android | `spaced-android` | top | 30 | on |

`overlays/usr/share/spaced-themes/themes.json` is the runtime source for `panel_layout`, `panel_position`, `panel_size`, optional `panel_color`, and `cairo_dock`.

## Runtime behavior

`spaced-switch-theme` operates on existing toplevel IDs named `bottom` and `top` when those schemas exist. For each one it sets:

```text
orientation
size
background/type
background/color
background/opacity
y
y-bottom
```

For a top panel:

```text
y = 0
y-bottom = -1
```

For a bottom panel:

```text
y = -1
y-bottom = 0
```

The helper never runs `mate-panel --replace`. Replacing the process during a theme switch can lose the notification-area X selection and break tray applets.

Changing the `default-layout` key does not itself rebuild an existing user's panel. It identifies the layout for new/reset profiles; the helper's orientation and size writes handle normal theme changes.

## Panel color channels

Panel color is not controlled in one place.

### GTK3 widget surface

The active GTK theme paints panel widgets through selectors in `spaced-overrides.css` and the theme's own `gtk.css`, using:

```text
@panel_bg_color
@panel_fg_color
```

This controls labels, menus, applet plugs, buttons, and related child widgets.

### Explicit MATE toplevel background

Three themes currently set a `panel_color` in `themes.json`:

| Theme | Explicit toplevel background |
|---|---|
| Spaced Linux Dark | `#2f2f2f` |
| Windows 11 Dark | `#17243b` |
| Android | `#263238` |

For those themes the helper writes:

```text
type = color
color = <panel_color>
opacity = 65535
```

For other themes it writes `type = none`, allowing GTK CSS to provide the outer appearance.

The toplevel background and GTK widget CSS are independent. Diagnose the outer panel surface separately from applet and button surfaces.

### GTK2 panel colors

Legacy panel-related GTK2 widgets use `panel_bg_color` and `panel_fg_color` from the active theme's `gtk-2.0/gtkrc`.

## Theme-specific panel rules

Several themes intentionally add more than a palette change:

- **Windows 11 Dark** uses flat rounded taskbar buttons, translucent hover/checked surfaces, and a thin active indicator.
- **Windows XP** uses a saturated blue Luna taskbar gradient and a green Brisk/Start button gradient.
- **GeoWorks** expands selectors so separate applet plug processes receive the dark-cyan surface.
- **Spaced Linux Dark and Light** remain visually restrained and use their semantic panel palette.

When changing a panel color, inspect both the semantic palette and any theme-specific selectors near the end of that theme's `gtk.css`.

## Cairo Dock

Cairo Dock is enabled only for macOS and Android.

On first use, `spaced-switch-theme`:

1. copies the upstream `Default-Single` theme into `~/.config/cairo-dock/current_theme`;
2. replaces its launchers with the Spaced launcher set;
3. clears the configured module list and uses normal visibility;
4. starts Cairo Dock with the software backend used by the project.

When a non-dock theme is selected, the helper stops the user's `cairo-dock` process.

The dock is not part of the MATE panel process, and its colors are not guaranteed to match every GTK panel rule.

## Defaults

The GSettings override establishes:

```ini
[org.mate.panel]
default-layout='spaced-linux'

[org.mate.panel.applet.clock]
format='12-hour'
show-date=false
```

The repository does not currently ship `/etc/dconf/db/local.d/01-spaced` or `02-panel`, and it does not define Fahrenheit or mph panel-clock unit defaults in the Spaced override. Do not cite those as current sources.

## Verification

Check the registry:

```bash
python3 - <<'PY'
import json
from pathlib import Path

for theme in json.loads(Path("overlays/usr/share/spaced-themes/themes.json").read_text())["themes"]:
    print(
        theme["id"],
        theme["panel_layout"],
        theme["panel_position"],
        theme["panel_size"],
        theme.get("panel_color", "CSS"),
        "dock" if theme["cairo_dock"] else "no-dock",
    )
PY
```

Inspect the live panel:

```bash
gsettings get org.mate.panel default-layout

gsettings get \
  org.mate.panel.toplevel:/org/mate/panel/toplevels/bottom/ \
  orientation

gsettings get \
  org.mate.panel.toplevel:/org/mate/panel/toplevels/bottom/ \
  size

gsettings get \
  org.mate.panel.toplevel:/org/mate/panel/toplevels/bottom/background/ \
  type
```

After a theme change, verify:

- the panel is on the intended edge;
- it remains 30 px high unless the registry was deliberately changed;
- all six applets remain present;
- the notification area still owns its tray selection;
- the outer toplevel and child applet surfaces both have the intended colors;
- macOS and Android start the dock, while other themes stop it.
