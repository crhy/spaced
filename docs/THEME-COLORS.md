# Spaced Linux theme and interface color reference

This document inventories the color-bearing parts of the Spaced Linux desktop at commit `f462bdb4b4d3916caf1617159056f2743b016acf`.

It covers the ten selectable MATE metathemes, the internal `Spaced-Dark` engine, GTK2 and GTK3, window decorations, panel backgrounds, icons, wallpapers, terminal colors, Compiz presentation colors, LightDM, Flatpak propagation, and cross-toolkit settings.

For architecture, runtime flow, installation, and testing, see [MATE-theming.md](MATE-theming.md).

## Scope and terminology

Spaced Linux has:

- **ten selectable metathemes** registered in `themes.json`;
- **one internal engine directory**, `Spaced-Dark`, which is not a selectable top-level MATE metatheme;
- **eleven `Spaced-Icons-*` directories**, including an internal `Spaced-Icons-Spaced-Dark` overlay;
- two shared menu/panel icon overlays;
- a hicolor fallback area for Spaced application and symbolic assets.

Paths in this document are repository paths beneath `overlays/`. Remove the leading `overlays/` to get the installed filesystem path.

## Where colors are stored

| Visual area | Primary source |
|---|---|
| GTK3 semantic palette | `usr/share/themes/Spaced-<Name>/gtk-3.0/gtk.css` |
| General GTK3 widgets | `usr/share/themes/Spaced-Dark/gtk-3.0/gtk-widgets.css` |
| Check boxes and radio buttons | shared `gtk-widgets-assets.css`, then each theme's tail rules |
| Switches and modern shared fixes | `usr/share/themes/Spaced-Dark/gtk-3.0/spaced-overrides.css` |
| Inactive/backdrop states | `usr/share/themes/Spaced-Dark/gtk-3.0/gtk-widgets-backdrop.css` |
| GTK2 palette | each theme's `gtk-2.0/gtkrc` |
| GTK2 shared drawing rules | `usr/share/themes/Spaced-Dark/gtk-2.0/gtkrc-shared` |
| Titlebar and frame colors | GTK3 `wm_*` variables consumed by `metacity-theme-3.xml` |
| Legacy titlebar drawing | `metacity-theme-1.xml` and its literal colors/assets |
| Panel widget colors | GTK3 `@panel_bg_color` / `@panel_fg_color` |
| Explicit panel toplevel color | optional `panel_color` in `usr/share/spaced-themes/themes.json` |
| Folder/home icon colors | `usr/share/icons/Spaced-Icons-*/scalable/places/*.svg` |
| Menu and trash icon colors | `usr/share/icons/Spaced-Menu-On-{Dark,Light}/` |
| Wallpaper fallback colors | metatheme `index.theme` and `mate-background-properties/spaced-linux.xml` |
| Terminal defaults | `90_spaced-linux.gschema.override` |
| Terminal light/dark switch | `usr/local/bin/spaced-switch-theme` |
| Compiz cube/skydome | `etc/skel/.config/compiz/compizconfig/Default.ini` |
| Qt Quick Controls | `etc/xdg/QtProject/qtquickcontrols2.conf` |
| LightDM | `etc/lightdm/lightdm-gtk-greeter.conf` |
| Appearance theme cards | static `usr/share/themes/Spaced-*/preview.png` |

## GTK3 palette roles

Every theme defines the same main semantic roles before importing the shared engine:

| Variable | Meaning |
|---|---|
| `theme_bg_color` | ordinary window and widget surface |
| `theme_fg_color` | ordinary foreground on `theme_bg_color` |
| `theme_base_color` | editable/list/content surface |
| `theme_text_color` | text on `theme_base_color` |
| `theme_selected_bg_color` | general selection/accent background |
| `theme_selected_fg_color` | foreground on the general selection background |
| `theme_tooltip_bg_color` / `theme_tooltip_fg_color` | tooltip surface and text |
| `link_color` / `link_visited_color` | links |
| `success_color` / `error_color` | semantic success and error accents |
| `titlebar_*`, `menubar_*`, `toolbar_*`, `menu_*` | component-specific surfaces and foregrounds |
| `panel_bg_color` / `panel_fg_color` | panel widget surface and foreground |
| `tab_checked_color` | selected notebook/tab accent |
| `osd_*` | on-screen display palette |
| `backdrop_selected_*` | inactive-window selection colors |
| `wm_*` | Metacity/Marco/GTK window-decorator colors |

Shared widget CSS derives many final colors with GTK functions such as `shade()`, `mix()`, and `alpha()`. A literal table therefore describes the palette inputs, not every rendered pixel.

## GTK3 core surfaces and selections

| Theme directory | Background / foreground | Base / text | Selection / selection foreground | Tooltip background / foreground |
|---|---|---|---|---|
| `Spaced-Dark` (internal) | `#383838` / `#dedede` | `#333333` / `#eeeeee` | `#5588ee` / `#ffffff` | `#111111` / `#dedede` |
| `Spaced-Linux-Dark` | `#2f2f2f` / `#dedede` | `#272727` / `#eeeeee` | `#707070` / `#ffffff` | `#111111` / `#dedede` |
| `Spaced-Linux-Light` | `#f3f3f3` / `#1f1f1f` | `#ffffff` / `#1f1f1f` | `#666666` / `#ffffff` | `#111111` / `#1f1f1f` |
| `Spaced-Android` | `#263238` / `#e0e0e0` | `#20292d` / `#f0f0f0` | `#82bbc4` / `#ffffff` | `#263238` / `#ffffff` |
| `Spaced-Geoworks` | `#d6d6c6` / `#101010` | `#f2f2e8` / `#000000` | `#006f70` / `#ffffff` | `#ffffcc` / `#000000` |
| `Spaced-MacOS` | `#f5f5f7` / `#1d1d1f` | `#ffffff` / `#1d1d1f` | `#007aff` / `#ffffff` | `#f5f5f7` / `#1d1d1f` |
| `Spaced-Mint` | `#2b2b2b` / `#dedede` | `#1d1d1d` / `#f0f0f0` | `#86a650` / `#ffffff` | `#111111` / `#dedede` |
| `Spaced-Win11-Dark` | `#17243b` / `#f3f3f3` | `#111827` / `#ffffff` | `#60cdff` / `#000000` | `#17243b` / `#f3f3f3` |
| `Spaced-Win11-Light` | `#f3f3f3` / `#1f1f1f` | `#ffffff` / `#1f1f1f` | `#005fb8` / `#ffffff` | `#ffffff` / `#333333` |
| `Spaced-Win311` | `#c0c0c0` / `#000000` | `#c0c0c0` / `#000000` | `#000080` / `#ffffff` | `#ffffcc` / `#000000` |
| `Spaced-WinXP` | `#ece9d8` / `#000000` | `#ffffff` / `#000000` | `#316ac5` / `#ffffff` | `#ffffcc` / `#000000` |

The Spaced Linux Light tooltip palette is currently `#111111` background with `#1f1f1f` foreground, which has poor contrast. This table records the committed value; it is not an endorsement of that pairing.

## GTK3 accents, panel, and window-decoration inputs

| Theme | Link / visited | Success / error | Checked-tab accent | Panel background / foreground | `wm_bg` / focused title / unfocused title |
|---|---|---|---|---|---|
| `Spaced-Dark` | `#5588ee` / `#2a76c6` | `#4e9a06` / `#cc0000` | `#215d9c` | `#383838` / `#dedede` | `#383838` / `mix(#dedede,#383838,0.1)` / `mix(#dedede,#383838,0.6)` |
| `Spaced-Linux-Dark` | `#5588ee` / `#2a76c6` | `#4e9a06` / `#cc0000` | `#c0c0c0` | `#2f2f2f` / `#dedede` | `#2a2a2a` / `#dedede` / `#888888` |
| `Spaced-Linux-Light` | `#5588ee` / `#2a76c6` | `#4e9a06` / `#cc0000` | `#c0c0c0` | `#e6e6e6` / `#1f1f1f` | `#f0f0f0` / `#1f1f1f` / `#888888` |
| `Spaced-Android` | `#82bbc4` / `#4a90d9` | `#34a853` / `#ea4335` | `#82bbc4` | `#263238` / `#e0e0e0` | `#202020` / `#e0e0e0` / `#888888` |
| `Spaced-Geoworks` | `#008284` / `#006060` | `#00aa00` / `#ff0000` | `#008284` | `#004040` / `#ffffff` | `#004040` / `#ffffff` / `#88aaaa` |
| `Spaced-MacOS` | `#007aff` / `#5856d6` | `#34c759` / `#ff3b30` | `#007aff` | `#e9e9ec` / `#1d1d1f` | `#e9e9ec` / `mix(#1d1d1f,#e9e9ec,0.1)` / `mix(#1d1d1f,#e9e9ec,0.6)` |
| `Spaced-Mint` | `#86a650` / `#57782e` | `#86a650` / `#cc0000` | `#86a650` | `#303030` / `#dedede` | `#2a2a2a` / `mix(#dedede,#2a2a2a,0.1)` / `mix(#dedede,#2a2a2a,0.6)` |
| `Spaced-Win11-Dark` | `#60cdff` / `#4a90d9` | `#4e9a06` / `#cc0000` | `#60cdff` | `#17243b` / `#f3f3f3` | `#17243b` / `#f3f3f3` / `#9a9a9a` |
| `Spaced-Win11-Light` | `#005fb8` / `#4a4a4a` | `#4e9a06` / `#cc0000` | `#005fb8` | `#e6e6e6` / `#1f1f1f` | `#ffffff` / `#1f1f1f` / `#666666` |
| `Spaced-Win311` | `#0000ff` / `#800080` | `#008000` / `#ff0000` | `#ffffff` | `#c0c0c0` / `#000000` | `#000080` / `#ffffff` / `#c0c0c0` |
| `Spaced-WinXP` | `#3c9a3c` / `#800080` | `#4e9a06` / `#cc0000` | `#3c9a3c` | `#235edc` / `#ffffff` | `#235edc` / `#ffffff` / `#b0c4e8` |

`wm_border_focused` and `wm_border_unfocused` are generally darker `shade()` values of `wm_bg`; Windows 3.11 uses literal white and gray borders.

## Informational and warning colors

Most themes share these legacy semantic backgrounds:

```text
information: rgb(252,246,202), black foreground
warning:     rgb(250,173,61), black foreground
question:    rgb(85,136,238), white foreground
error box:   rgb(237,54,54), white foreground
```

Because these roles are colored, “Spaced Linux Dark and Light are monochrome” should be understood as a design target for ordinary chrome and controls, not a claim that every semantic warning or error surface contains no hue.

## Check boxes and radio buttons

### Shared base mechanics

`Spaced-Dark/gtk-3.0/gtk-widgets-assets.css` defines the shared `check` and `radio` nodes:

```css
check,
radio {
    min-width: 14px;
    min-height: 14px;
    margin: 1px 4px;
    border: 1px solid mix(@theme_fg_color, @theme_bg_color, 0.55);
    background-color: @theme_base_color;
    background-image: none;
    color: @theme_selected_fg_color;
    -gtk-icon-source: none;
    -gtk-icon-shadow: none;
    box-shadow: inset 0 1px alpha(@theme_fg_color, 0.08);
}
```

Shapes:

```css
check { border-radius: 2px; }
radio { border-radius: 50%; }
```

The `background-image: none` reset prevents GTK fallback gradients from covering the theme's `background-color`. The `-gtk-icon-source: none` reset prevents a fallback glyph from leaking into unchecked states.

Hover state:

```text
border = theme_fg_color
fill   = mix(theme_fg_color, theme_base_color, 0.12)
```

Disabled state:

```text
border = mix(theme_fg_color, theme_bg_color, 0.30)
fill   = mix(theme_bg_color, theme_fg_color, 0.08)
mark   = mix(theme_fg_color, theme_bg_color, 0.35)
```

Menu-item indicators remove the border and surface and remain transparent.

### Glyph names

The shared engine requests:

| State | Symbolic icon name |
|---|---|
| checked checkbox | `object-select-symbolic` |
| indeterminate checkbox | `list-remove-symbolic` |
| checked or indeterminate radio | `media-record-symbolic` |

Spaced ships hicolor fallback SVGs for these names. The active icon theme's inheritance chain is searched before hicolor, so the final asset may come from another inherited theme. Symbolic results use the CSS node's `color` at render time.

### Checked colors

| Theme | Checked fill | Checked border | Mark/dot | Shape note |
|---|---|---|---|---|
| `Spaced-Dark` | `#c8c8c8` | `#9a9a9a` | `#000000` | shared checkbox shape; circular radio |
| `Spaced-Linux-Dark` | `#c8c8c8` | `#9a9a9a` | `#000000` | monochrome |
| `Spaced-Linux-Light` | `#4a4a4a` | `#333333` | `#ffffff` | monochrome |
| `Spaced-Mint` | `#35a854` | `#298141` | `#ffffff` | Mint-Y Dark-style green |
| `Spaced-Android` | `#009688` | `#00766c` | `#ffffff` | Material teal |
| `Spaced-Geoworks` | `#008080` | `#006060` | `#ffffff` | classic dark cyan |
| `Spaced-Win311` | `#ffffff` | `#808080` | `#000000` | checked checkbox forced square; radio stays circular |
| `Spaced-MacOS` | `#007aff` | `#0062cc` | `#ffffff` | explicit 3 px checkbox radius |
| `Spaced-WinXP` | `#316ac5` | `#27559e` | `#ffffff` | explicit 3 px checkbox radius |
| `Spaced-Win11-Light` | `#005fb8` | `#004c93` | `#ffffff` | explicit 3 px checkbox radius |
| `Spaced-Win11-Dark` | `#60cdff` | `#4da4cc` | `#000000` | explicit 3 px checkbox radius |

Seven themes use one combined selector for checked and indeterminate states. The four themes with explicit legacy `check:checked, radio:checked` blocks do not override indeterminate borders.

### Indeterminate colors

| Theme | Indeterminate fill | Indeterminate border | Mark |
|---|---|---|---|
| `Spaced-Dark` | `#c8c8c8` | `#9a9a9a` | `#000000` |
| `Spaced-Linux-Dark` | `#c8c8c8` | `#9a9a9a` | `#000000` |
| `Spaced-Linux-Light` | `#4a4a4a` | `#333333` | `#ffffff` |
| `Spaced-Mint` | `#35a854` | `#298141` | `#ffffff` |
| `Spaced-Android` | `#009688` | `#00766c` | `#ffffff` |
| `Spaced-Geoworks` | `#008080` | `#006060` | `#ffffff` |
| `Spaced-Win311` | `#ffffff` | `#808080` | `#000000` |
| `Spaced-MacOS` | `#007aff` | `#007aff` | `#ffffff` |
| `Spaced-WinXP` | `#316ac5` | `#316ac5` | `#ffffff` |
| `Spaced-Win11-Light` | `#005fb8` | `#005fb8` | `#ffffff` |
| `Spaced-Win11-Dark` | `#60cdff` | `#60cdff` | `#000000` |

The last four rows use the shared `theme_selected_*` values for indeterminate states because their local tail rules target checked states only.

### Maintenance recommendation

The colors are functional, but the four explicit checked-only blocks duplicate shared shape rules. A future cleanup can normalize all themes to one combined checked/indeterminate selector while keeping the Windows 3.11 square-checkbox exception separate.

## Switches

Switches are not defined in `gtk-widgets-assets.css`. They are handled by `Spaced-Dark/gtk-3.0/spaced-overrides.css`.

Base switch:

```text
minimum size = 44 x 24 px
border       = shade(theme_bg_color, 0.70)
fill         = shade(theme_bg_color, 0.82)
radius       = 14 px
```

Checked switch:

```text
border = shade(theme_selected_bg_color, 0.82)
fill   = theme_selected_bg_color
```

Slider:

```text
minimum size = 20 x 20 px
fill         = theme_base_color
border       = shade(theme_bg_color, 0.62)
shadow       = alpha(#000000, 0.35)
```

Checked slider:

```text
fill   = theme_selected_fg_color
border = shade(theme_selected_bg_color, 0.70)
```

Disabled switches use `opacity: 0.55`.

## General GTK3 literals outside the palettes

Most shared GTK3 rules use semantic variables. A few shared rules still carry literal colors, including scrollbar, treeview, and textview values in `gtk-widgets.css`, black-alpha shadows in `spaced-overrides.css`, and white/black literals in application compatibility files.

Theme-specific files intentionally contain additional literals for OS emulation. Examples include:

- Windows XP's Luna taskbar, Start button, Brisk Menu, notebook, and button gradients;
- Windows 11 Dark's translucent panel hover/checked surfaces;
- Windows 3.11's white notebook key line and square checks;
- macOS Aqua checked controls;
- Android Material teal controls.

When an application ignores a palette change, search both the shared engine and the active theme's tail for a literal override.

## GTK2 color schemes

Each `gtk-2.0/gtkrc` defines eight named colors in this order:

```text
bg_color
fg_color
base_color
text_color
selected_bg_color
selected_fg_color
panel_bg_color
panel_fg_color
```

| Theme | GTK2 scheme in that order |
|---|---|
| `Spaced-Dark` | `#383838 / #dedede / #333333 / #eeeeee / #5588ee / #ffffff / #383838 / #dedede` |
| `Spaced-Linux-Dark` | `#2f2f2f / #dedede / #272727 / #eeeeee / #707070 / #ffffff / #2f2f2f / #dedede` |
| `Spaced-Linux-Light` | `#f3f3f3 / #1f1f1f / #ffffff / #1f1f1f / #666666 / #ffffff / #e6e6e6 / #1f1f1f` |
| `Spaced-Android` | `#263238 / #e0e0e0 / #20292d / #f0f0f0 / #82bbc4 / #ffffff / #263238 / #ffffff` |
| `Spaced-Geoworks` | `#d6d6c6 / #101010 / #f2f2e8 / #000000 / #006f70 / #ffffff / #004040 / #ffffff` |
| `Spaced-MacOS` | `#f5f5f7 / #1d1d1f / #ffffff / #1d1d1f / #007aff / #ffffff / #e9e9ec / #1d1d1f` |
| `Spaced-Mint` | `#2b2b2b / #dedede / #1d1d1d / #f0f0f0 / #86a650 / #ffffff / #303030 / #dedede` |
| `Spaced-Win11-Dark` | `#17243b / #f3f3f3 / #111827 / #ffffff / #60cdff / #000000 / #17243b / #f3f3f3` |
| `Spaced-Win11-Light` | `#f3f3f3 / #1f1f1f / #ffffff / #1f1f1f / #005fb8 / #ffffff / #e6e6e6 / #1f1f1f` |
| `Spaced-Win311` | `#c0c0c0 / #000000 / #ffffff / #000000 / #000080 / #ffffff / #000080 / #ffffff` |
| `Spaced-WinXP` | `#ece9d8 / #000000 / #ffffff / #000000 / #316ac5 / #ffffff / #245edb / #ffffff` |

Known GTK2/GTK3 differences include:

- Windows 3.11 GTK2 base is white, while GTK3 base is `#c0c0c0`;
- Android GTK2 panel foreground is white, while GTK3 panel foreground is `#e0e0e0`;
- Windows XP GTK2 panel blue is `#245edb`, while the GTK3 semantic panel background is `#235edc` and the actual taskbar uses a multi-stop gradient.

The per-theme `gtkrc` is the normal source for GTK2. Theme switching does not currently write a session `gtk-color-scheme` key.

## Window decorations

Compiz is the window manager and compositor. Its decoration plugin runs `gtk-window-decorator --replace`.

The selected decoration theme comes from:

```text
org.mate.Marco.general theme
```

Each selectable theme includes:

```text
metacity-1/metacity-theme-1.xml
metacity-1/metacity-theme-3.xml
```

The version-3 files bind to GTK palette values with expressions such as:

```text
gtk:custom(wm_border_focused,...)
gtk:custom(wm_border_unfocused,...)
gtk:custom(wm_title_focused,...)
gtk:custom(wm_title_unfocused,...)
```

Changing `wm_*` in `gtk.css` therefore changes version-3 titlebar and border colors without editing every XML drawing operation.

The version-1 files contain more hard-coded drawing colors and must be checked separately when supporting older decoration paths.

Window button assets and geometry also live under `metacity-1/`. A palette-only change should not casually alter hitbox geometry.

## Panel colors

Panel appearance has three distinct channels.

### 1. GTK3 panel widget CSS

Shared and per-theme selectors paint panel surfaces, applets, labels, and buttons from:

```text
@panel_bg_color
@panel_fg_color
```

Special cases:

- Windows 11 Dark uses quiet translucent hover/checked button surfaces and a 2 px active indicator.
- Windows XP uses a blue taskbar gradient and a green Start/Brisk button gradient.
- GeoWorks expands panel selectors to keep separate applet plugs on the dark-cyan surface.

### 2. MATE toplevel background

`spaced-switch-theme` writes an explicit toplevel color only when `themes.json` has `panel_color`:

| Theme ID | Explicit toplevel color |
|---|---|
| `linux-dark` | `#2f2f2f` |
| `win11-dark` | `#17243b` |
| `android` | `#263238` |

Other themes set the toplevel background type to `none`, allowing GTK CSS to show through.

The explicit toplevel surface and GTK widget CSS are separate. A panel may have the right outer background but wrong applet/button colors, or vice versa.

### 3. GTK2 panel palette

Legacy panel widgets use `panel_bg_color` and `panel_fg_color` from the active GTK2 `gtkrc`.

## MATE metatheme fallback background colors

The top-level `index.theme` files carry `BackgroundColor` values used with the suggested `BackgroundImage`:

| Selectable theme | Metatheme `BackgroundColor` |
|---|---|
| Spaced Linux Dark | `#1a1a1a` |
| Spaced Linux Light | `#f0f0f0` |
| Android | `#303030` |
| GeoWorks | `#d6d6c6` |
| macOS | `#dce8f5` |
| Mint | `#1d1d1d` |
| Windows 11 Light | `#e8eef7` |
| Windows 11 Dark | `#202020` |
| Windows 3.11 | `#008080` |
| Windows XP | `#6b8e3f` |

These values are not necessarily identical to the wallpaper catalog's `pcolor`; they are maintained in separate files.

## Wallpaper catalog fallback colors

`usr/share/mate-background-properties/spaced-linux.xml` registers:

| Wallpaper | Solid fallback |
|---|---|
| `SpacedBack.jpg` | `#1a1a1a` |
| `SpacedBackLight.jpg` | `#f0f0f0` |
| `SimpleBackb.png` | `#17181d` |
| `spaced-orbit-4k.png` | `#050912` |
| `linuxmint.jpg` | `#1d1d1d` |
| `macos.jpg` | `#3a3a3a` |
| `win311.jpg` | `#808080` |
| `winxp.jpg` | `#235edc` |
| `win11light.jpg` | `#f3f3f3` |
| `win11dark.jpg` | `#0d1430` |
| `geoworks.jpg` | `#404040` |
| `android.jpg` | `#303030` |
| `bluecanvas.jpg` | `#1a3a5c` |
| `euclidgalacticcore.jpg` | `#0a0a1a` |
| `solarsystem.jpg` | `#1a1a2e` |

The default GSettings background is `SpacedBack.jpg` with primary color `#1a1a1a`.

## Icon colors

### Folder/home overlays

| Icon theme | Main folder fill |
|---|---|
| `Spaced-Icons-Spaced-Dark` (internal) | `#777777` |
| `Spaced-Icons-Linux-Dark` | `#8e8e8e` |
| `Spaced-Icons-Linux-Light` | `#aab2bd` |
| `Spaced-Icons-MacOS` | `#4a90e2` |
| `Spaced-Icons-Android` | `#26a69a` |
| `Spaced-Icons-WinXP` | `#d6b35a`, with `#f3dc91` two-tone detail |
| `Spaced-Icons-Win11-Dark` | `#3979c9` |
| `Spaced-Icons-Win11-Light` | `#5294e2` |
| `Spaced-Icons-Win311` | `#d2aa45` |
| `Spaced-Icons-Geoworks` | `#607d8b` |
| `Spaced-Icons-Mint` | `#86a650` |

Each overlay owns scalable `folder.svg`, `user-desktop.svg`, `user-home.svg`, and `user-home-open.svg` assets. The runtime does not recolor Papirus folders or rewrite symlinks.

Linux Dark and Linux Light also own additional application, device, mimetype, and status icons. Other themes inherit those categories.

### Menu and trash overlays

| Asset | Dark-surface overlay | Light-surface overlay |
|---|---|---|
| `start-here.svg` and symbolic variant | `#f3f3f3` | `#202020` |
| trash assets | gray family including `#6b7280` and `#e5e7eb` | dark gray family including `#111827`, `#4b5563`, and `#6b7280` |

### Brand and application assets

The hicolor and pixmap areas contain project branding with their own literals, including the blue Spaced mark `#5588ee`, white elements, gray installer artwork, user-face images, and raster logos. These colors do not follow the active GTK palette.

## Terminal colors

### Schema defaults

`90_spaced-linux.gschema.override` establishes:

```text
background = #000000
foreground = #888888
bold       = #ffffff
use-theme-colors = false
```

Default 16-color palette:

```text
#000000 #cc0000 #4e9a06 #c4a000
#3465a4 #75507b #06989a #d3d7cf
#555753 #ef2929 #8ae234 #fce94f
#729fcf #ad7fa8 #34e2e2 #eeeeee
```

### Theme-switch behavior

`spaced-switch-theme` rewrites only the default profile's background and foreground:

| `dark` in `themes.json` | Background | Foreground |
|---|---|---|
| `true` | `#000000` | `#888888` |
| `false` | `#ffffff` | `#000000` |

The helper does not rewrite the bold color or 16-color palette on every switch; those are schema defaults unless the user changes them.

Dark registry entries are Linux Dark, Mint, Windows 11 Dark, and Android.

## Compiz presentation colors

The seeded INI profile contains colors independent of GTK:

```text
cube background            = #000000ff
skydome gradient start     = #000000ff
skydome gradient end       = #00194aff
```

These live in:

```text
etc/skel/.config/compiz/compizconfig/Default.ini
```

The current Compiz backend is INI, not a Spaced-owned `org.compiz.*` dconf profile.

## Cross-toolkit colors and limitations

### LibreOffice

`SAL_USE_VCLPLUGIN=gtk3` requests GTK3 integration. Actual rendering still depends on LibreOffice's GTK3 VCL behavior.

### Qt Widgets

`QT_QPA_PLATFORMTHEME=gtk3` requests GTK platform integration for Qt Widgets applications.

### Qt Quick Controls

Qt Quick Controls are fixed to:

```text
style  = Universal
theme  = Dark
accent = #cfd3d8
```

This setting does not switch to a light Qt Quick theme when the active Spaced theme is light.

### GTK4 and libadwaita

GTK4 and libadwaita applications do not consume these GTK3 CSS files. They are outside the guaranteed visual coverage of the Spaced GTK3 engine.

## Flatpak propagation

For registered theme switches, Spaced copies all `/usr/share/themes/Spaced-*` directories into `~/.local/share/themes`, grants read access, and sets a Flatpak `GTK_THEME` override.

Consequences:

- the user-local copy can shadow `/usr/share/themes`;
- a package update can be invisible to Flatpaks until the export is refreshed;
- GTK3 Flatpaks may follow the theme;
- GTK4/libadwaita and Qt Flatpaks are not guaranteed to follow it.

## LightDM colors

The greeter uses a fixed configuration:

```text
background       = SimpleBackb.png
theme            = Spaced-Dark
icon theme       = Papirus-Dark
default user art = spaced-linux.png
logo             = spaced-logo.png
```

The selected desktop metatheme does not alter the greeter.

## Static Appearance previews

Each theme directory currently includes `preview.png`. These PNGs are independent of live GTK CSS and icon resolution.

A control-color change can therefore produce either of these mismatches:

- live controls are correct but the Appearance card is stale;
- the card looks correct but the installed live CSS is stale.

Always test both artifacts. Do not use the card alone to diagnose GTK rendering.

## Default GSettings values carrying visual choices

The Spaced override sets, among other values:

```text
org.mate.interface gtk-theme             Spaced-Linux-Dark
org.mate.interface icon-theme            Spaced-Icons-Linux-Dark
org.gnome.desktop.interface gtk-theme     Spaced-Linux-Dark
org.gnome.desktop.interface icon-theme    Spaced-Icons-Linux-Dark
org.gnome.desktop.interface color-scheme  prefer-dark
org.mate.Marco.general theme              Spaced-Linux-Dark
org.mate.background picture-filename      SpacedBack.jpg
org.mate.background primary-color         #1a1a1a
org.mate.panel default-layout             spaced-linux
```

These are defaults for new profiles. Existing user dconf values take precedence.

## Quick edit reference

| Goal | Edit |
|---|---|
| Change a theme's ordinary GTK3 colors | `themes/Spaced-<Name>/gtk-3.0/gtk.css` palette |
| Change checked check/radio colors | the active theme's tail selectors in `gtk.css` |
| Change shared unchecked/hover/disabled control states | `Spaced-Dark/gtk-3.0/gtk-widgets-assets.css` |
| Stop a fallback image from covering controls | ensure `background-image: none` remains in the shared indicator rules |
| Change switch colors or geometry | `Spaced-Dark/gtk-3.0/spaced-overrides.css` |
| Change ordinary button, entry, menu, or tree rules | `Spaced-Dark/gtk-3.0/gtk-widgets.css` |
| Change inactive-window states | `Spaced-Dark/gtk-3.0/gtk-widgets-backdrop.css` |
| Change GTK2 colors | the active theme's `gtk-2.0/gtkrc` |
| Change titlebar/frame palette | active theme's `wm_*` colors |
| Change titlebar drawing or geometry | active theme's `metacity-1/*.xml` and assets |
| Change panel widget colors | active GTK3 palette and panel selectors |
| Change explicit panel outer surface | `themes.json` `panel_color` |
| Change folder/home colors | matching `Spaced-Icons-*` SVGs |
| Change control glyph fallback art | hicolor symbolic action SVGs |
| Change wallpaper catalog fallback | `mate-background-properties/spaced-linux.xml` |
| Change a theme's suggested wallpaper | top-level `index.theme` and `themes.json` |
| Change terminal defaults | GSettings override |
| Change terminal light/dark behavior | `spaced-switch-theme` |
| Change Compiz cube/skydome | skel Compiz `Default.ini` |
| Change Qt Quick appearance | `qtquickcontrols2.conf` |
| Change login screen | `lightdm-gtk-greeter.conf` |
| Change Appearance card | static `preview.png` |

## Verification checklist

After a visual change:

1. Run `make check`.
2. Build and explicitly install `spaced-mate-default-settings` on the test system.
3. Confirm `/usr/share/themes` matches the checkout.
4. Confirm no user-local theme copy shadows the installed file.
5. Start a new GTK3 process and test real controls.
6. Test a GTK2 application when the GTK2 palette should match.
7. Test `gtk-window-decorator` titlebars.
8. Test the panel and any special Brisk rules.
9. Refresh and test the Flatpak export.
10. Inspect and update `preview.png` separately.
