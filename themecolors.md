# Spaced Linux 8.26.4 — Complete Theme & Interface Color Reference

Every place a color is defined for the Spaced Linux desktop experience —
GTK3 and GTK2 themes, window decorations, panel, icon themes, wallpapers,
terminal, dock, cross-toolkit apps, Flatpak propagation, and the session
settings that tie them together.

**Applicable stack (Devuan Ceres, the "unstable" suite = Debian sid):**

| Layer | Package / version (Ceres) |
|---|---|
| Widget toolkit | GTK 3.24 (3.24.5x) — MATE is GTK3/X11 only; GTK4 does not apply |
| Desktop | MATE 1.26/1.27 (mate-panel 1.27.x, mate-settings-daemon 1.26.x) |
| Window manager | Compiz 2:0.8.18 + `compiz-mate`; decorator: gtk-window-decorator (compiz-gnome, `marco` lib present) |
| Icon theme base | papirus-icon-theme |
| Dock | cairo-dock-core 3.5.1 |
| Display manager | lightdm + lightdm-gtk-greeter |

All paths below are relative to the repo `overlays/` tree (the ISO source of
truth); on the installed system the same files live under `/usr/share/…`,
except user state, which comes from `etc/skel/` → `/home/user`.

---

## 1. How a color reaches the screen — the pipeline

```
gsettings (dconf)  org.mate.interface.gtk-theme / icon-theme / color-scheme
                   org.mate.panel.toplevels.<id>.background.{type,color,opacity}
                   org.mate.Marco.general.theme        org.mate.background.*
        │                                                     │
        ▼                                                     ▼
mate-settings-daemon (xsettings plugin)                 gtk-window-decorator
writes XSETTINGS on _XSETTINGS_S0:                      (window frame colors)
  Net/ThemeName, Net/IconThemeName,                     reads marco/metacity theme
  Gtk/ColorScheme, Gtk/FontName, …                      (gtk:custom(wm_*) → GTK css)
        │                                                     │
        ▼                                                     ▼
GTK app: reads XSETTINGS → GtkSettings:gtk-theme-name    compiz: shadows/alpha
         (GTK_THEME env var overrides per-process)      (org.compiz.* gsettings)
        │
        ▼
CSS resolution order (last wins):
  1. theme css …/themes/<name>/gtk-3.0/gtk.css
  2. Spaced-Dark engine files it @imports (widgets, assets, backdrop, apps)
  3. per-theme tail rules appended in gtk.css (panel, checks, accents)
  4. user override ~/.config/gtk-3.0/gtk.css (always loaded on top)
```

Search paths GTK uses for `themes/<name>/gtk-3.0/gtk.css` (in order):
`~/.local/share/themes` → `~/.themes` → `$XDG_DATA_DIRS/themes`
(→ `/usr/local/share/themes`, `/usr/share/themes`) → built-in (Adwaita).
The loader steps the minor version down (3.24, 3.22, … 3.0), so every theme
only keeps a `gtk-3.0/` folder. Theme names are case-sensitive on disk.

**Precedence for any given GTK setting (low → high):** hard-coded default <
`settings.ini` files (`/etc/gtk-3.0` → system → `~/.config/gtk-3.0`) < the
theme's own `gtk-3.0/settings.ini` < XSETTINGS (mate-settings-daemon) <
`GTK_THEME` environment variable. On this desktop, settings flow through
gsettings exclusively — no `settings.ini`/`xsettingsd` files are shipped.

**X resources for non-GTK X apps:** mate-settings-daemon's *xrdb* plugin
merges `BACKGROUND`, `FOREGROUND`, `SELECT_BACKGROUND`, `SELECT_FOREGROUND`,
`WINDOW_BACKGROUND`, `WINDOW_FOREGROUND`, `HIGHLIGHT`, `LOWLIGHT` derived
from the active GTK style.

**Theme switching machinery:** `spaced-theme-monitor` (autostart) watches
`org.mate.interface gtk-theme` via `gsettings monitor`, maps it to a
`themes.json` id (case-insensitively) and runs
`/usr/local/bin/spaced-switch-theme <id>`, which then applies: wallpaper,
Brisk dark preference, toolkit color-scheme, MATE Terminal colors, panel
position/size/toplevel background color, cairo-dock start/stop, and Flatpak
theme export (see §11 & §13).

---

## 2. GTK3 theme engine — architecture

There are **11 themes** under `overlays/usr/share/themes/`. Only
**Spaced-Dark** contains the full GTK3 engine; the other 10 ship only
`gtk-3.0/gtk.css` + metatheme `index.theme` and pull the engine in with
relative imports (identical block in every theme):

```css
@import url("../../Spaced-Dark/gtk-3.0/gtk-widgets.css");
@import url("../../Spaced-Dark/gtk-3.0/gtk-widgets-assets.css");
@import url("../../Spaced-Dark/gtk-3.0/gtk-widgets-backdrop.css");
@import url("../../Spaced-Dark/gtk-3.0/apps/granite-widgets.css");
@import url("../../Spaced-Dark/gtk-3.0/apps/unity.css");
@import url("../../Spaced-Dark/gtk-3.0/apps/xfce.css");
@import url("../../Spaced-Dark/gtk-3.0/apps/lightdm-gtk-greeter.css");
@import url("../../Spaced-Dark/gtk-3.0/spaced-overrides.css");
```

### Engine files `Spaced-Dark/gtk-3.0/` and the colors they carry

| File | Role | Color content |
|---|---|---|
| `gtk.css` | Defines the theme's complete `@define-color` palette, panel surface rule, and tail overrides | See §3 per-theme tables |
| `gtk-widgets.css` (4,851 lines) | ~95% palette-driven widget rules using `@theme_*` + `shade()`/`mix()`/`alpha()` | Almost no raw hex. Only exceptions: scrollbar buttons `#a6a8a7` / hover `#cacbc9` / backdrop `#5d6262`; `treeview ~ scrollbar.vertical` border `#1c1f1f`; `textview text` background `#232729` (hover `#252a2c`) |
| `gtk-widgets-assets.css` (64 lines) | Check/radio/switch base shapes and glyphs | `check,radio`: 14×14px, `border: 1px solid mix(@theme_fg_color,@theme_bg_color,0.55)`, `background-color: @theme_base_color`, `color: @theme_selected_fg_color`; `check { border-radius: 2px }`, `radio { border-radius: 50% }`; checked → `background-color/border-color: @theme_selected_bg_color`; glyphs via `-gtk-icon-source: -gtk-icontheme("object-select-symbolic" / "list-remove-symbolic" / "media-record-symbolic")`; `background-image: none` and `-gtk-icon-source: none` reset (commit `00fe376`) so no bitmap assets are required |
| `gtk-widgets-backdrop.css` (172 lines) | All `:backdrop` states | Purely derived from `@backdrop_selected_bg_color` / `@theme_bg_color`; no literals |
| `spaced-overrides.css` (283 lines) | Cross-theme rules | Switch trough `shade(@theme_bg_color,0.82)`, checked fill `@theme_selected_bg_color`, slider `@theme_base_color`, shadow `alpha(#000000,0.35)`; buttons `mix(@theme_bg_color,@theme_fg_color,0.10)`; panel `@panel_bg_color`/`@panel_fg_color`, border `alpha(@panel_fg_color,0.18)`; caja desktop window transparent |
| `apps/*.css` | App-specific | `granite-widgets.css`: `alpha(#000,0.6)`/`#fff`; `unity.css`, `xfce.css`, `lightdm-gtk-greeter.css`: no hex values |

Each theme's `gtk-3.0/index.theme` also declares `gtk-theme-name = "Spaced-<N>"`.
The 10 user themes add a top-level `index.theme` of type `X-GNOME-Metatheme`
(see §7).

---

## 3. Per-theme GTK3 palettes (`gtk-3.0/gtk.css` `@define-color`)

All 11 themes define the same roles; values below are resolved literals.
`bg_ref` marks variables that alias `@theme_bg_color` instead of a literal.

### Spaced-Dark `#383838` base (also the engine owner)

| Variable | Value | Variable | Value |
|---|---|---|---|
| theme_bg_color | `#383838` | link_color | `#5588ee` |
| theme_fg_color | `#dedede` | link_visited_color | `#2a76c6` |
| theme_base_color | `#333333` | success_color | `#4e9a06` |
| theme_text_color | `#eeeeee` | error_color | `#cc0000` |
| theme_selected_bg_color | `#5588ee` | tab_checked_color | `#215d9c` |
| theme_selected_fg_color | `#ffffff` | osd | base `#333` / fg `#eee` / bg `alpha(#333,0.8)` |
| tooltip bg / fg | `#111111` / `#dedede` | backdrop_selected_bg | `shade(#383838,0.9)` |
| light / dark_shadow | `#444` / `#000` | backdrop_selected_fg | `#dedede` |
| info / warning | `rgb(252,246,202)` / `rgb(250,173,61)` | wm_bg | `#383838` |
| question / error bg | `rgb(85,136,238)` / `rgb(237,54,54)` | wm_title_focused | `mix(#dedede,#383838,0.1)` |
| titlebar/menubar/toolbar/menu/panel bg | `@theme_bg_color` | wm_title_unfocused | `mix(#dedede,#383838,0.6)` |
| …fg | `@theme_fg_color` | wm_border focused/unfocused | `shade(#383838,0.7/0.8)` |

### Theme palettes at a glance (full `@define-color` values)

`bg`=theme_bg_color, `fg`=theme_fg_color, `base`=theme_base_color,
`text`=theme_text_color, `sel`=theme_selected_bg_color,
`selfg`=theme_selected_fg_color, `tt`=tooltip, `link`=link_color,
`tab`=tab_checked_color, `panel`=panel_bg/fg, `wm`=wm_bg.

| Theme | bg / fg | base / text | sel / selfg | tt bg/fg | link | tab | panel | wm |
|---|---|---|---|---|---|---|---|---|
| Spaced-Linux-Dark | `#2f2f2f`/`#dedede` | `#272727`/`#eeeeee` | `#707070`/`#ffffff` | `#111111`/`#dedede` | `#5588ee` | `#c0c0c0` | @bg/@fg | `#2a2a2a` (unfocused `#888888`) |
| Spaced-Linux-Light | `#f3f3f3`/`#1f1f1f` | `#ffffff`/`#1f1f1f` | `#666666`/`#ffffff` | `#111111`/`#1f1f1f` | `#5588ee` | `#c0c0c0` | `#e6e6e6`/@fg | `#f0f0f0` |
| Spaced-Android | `#263238`/`#e0e0e0` | `#20292d`/`#f0f0f0` | `#82bbc4`/`#ffffff` | `#263238`/`#ffffff` | `#82bbc4` | `#82bbc4` | @bg/@fg | `#202020` (unfocused `#888888`) |
| Spaced-Geoworks | `#d6d6c6`/`#101010` | `#f2f2e8`/`#000000` | `#006f70`/`#ffffff` | `#ffffcc`/`#000000` | `#008284` | `#008284` | `#004040`/`#ffffff` | `#004040` (unfocused `#88aaaa`) |
| Spaced-MacOS | `#f5f5f7`/`#1d1d1f` | `#ffffff`/`#1d1d1f` | `#007aff`/`#ffffff` | `#f5f5f7`/`#1d1d1f` | `#007aff` | `#007aff` | `#e9e9ec`/@fg | `#e9e9ec` |
| Spaced-Mint | `#2b2b2b`/`#dedede` | `#1d1d1d`/`#f0f0f0` | `#86a650`/`#ffffff` | `#2b2b2b`/`#dedede` | `#86a650` | `#86a650` | `#303030`/@fg | `#2a2a2a` |
| Spaced-Win11-Dark | `#17243b`/`#f3f3f3` | `#111827`/`#ffffff` | `#60cdff`/**`#000000`** | `#17243b`/`#f3f3f3` | `#60cdff` | `#60cdff` | @bg/@fg | `#17243b` (unfocused `#9a9a9a`) |
| Spaced-Win11-Light | `#f3f3f3`/`#1f1f1f` | `#ffffff`/`#1f1f1f` | `#005fb8`/`#ffffff` | `#ffffff`/`#333333` | `#005fb8` | `#005fb8` | `#e6e6e6`/@fg | `#ffffff` (unfocused `#666666`) |
| Spaced-Win311 | `#c0c0c0`/`#000000` | `#c0c0c0`/`#000000` | `#000080`/`#ffffff` | `#ffffcc`/`#000000` | `#0000ff` | `#ffffff` | @bg/@fg | `#000080` (unfocused `#888888`) |
| Spaced-WinXP | `#ece9d8`/`#000000` | `#ffffff`/`#000000` | `#316ac5`/`#ffffff` | `#ffffcc`/`#000000` | `#3c9a3c` | `#3c9a3c` | `#235edc`/`#ffffff` | `#235edc` (unfocused `#b0c4e8`) |

Additional per-theme constants: `success_color` (Android `#34a853`,
MacOS `#34c759`, Win311 `#008000`, else `#4e9a06`), `error_color`
(Android `#ea4335`, MacOS `#ff3b30`, Win311 `#ff0000`, else `#cc0000`),
`link_visited_color` (MacOS `#5856d6`, Android `#4a90d9`, Win311 `#800080`,
WinXP `#800080`, Win11-Light `#4a4a4a`, else `#2a76c6`).

---

## 4. Check boxes, radio buttons, switches — the current colors

GTK3 renders indicators as CSS subnodes `check` / `radio` of
`checkbutton` / `radiobutton`. Shape and glyph come from the shared
`gtk-widgets-assets.css` (§2 — rounded 2px square / 50% circle, symbolic
glyph tinted by `color:`); each theme's `gtk.css` tail overrides the fill.

Two stylistic conventions coexist **as committed**:

1. **Refined (7 themes):** one combined selector
   `check:checked, check:indeterminate, radio:checked, radio:indeterminate`
   only overriding `background-color`, `border-color`, `color`. Shape stays
   engine default (2px check, 50% radio).
2. **Self-contained (4 themes):** `check:checked, radio:checked` setting
   `border: 1px solid` + explicit `border-radius: 3px` (check) and
   `border-radius: 50%` (radio).

| Theme | Fill | Border | Mark (symbolic glyph) |
|---|---|---|---|
| Spaced-Dark (1) | `#c8c8c8` | `#9a9a9a` | `#000000` |
| Spaced-Linux-Dark (1) | `#c8c8c8` | `#9a9a9a` | `#000000` |
| Spaced-Linux-Light (1) | `#4a4a4a` | `#333333` | `#ffffff` |
| Spaced-Mint (1) | `#35a854` | `#298141` | `#ffffff` |
| Spaced-Android (1) | `#009688` Material teal | `#00766c` | `#ffffff` |
| Spaced-Geoworks (1) | `#008080` GEOS teal | `#006060` | `#ffffff` |
| Spaced-Win311 (1, square: radius 0) | `#ffffff` | `#808080` | `#000000` |
| Spaced-MacOS (2) | `#007aff` Aqua | `#0062cc` | `#ffffff` |
| Spaced-WinXP (2) | `#316ac5` Luna | `#27559e` | `#ffffff` |
| Spaced-Win11-Light (2) | `#005fb8` | `#004c93` | `#ffffff` |
| Spaced-Win11-Dark (2) | `#60cdff` | `#4da4cc` | `#000000` |

**Unchecked indicators:** engine default everywhere — `background-color:
@theme_base_color`, `border: 1px solid mix(@theme_fg_color,@theme_bg_color,
0.55)`; hover → `mix(@theme_fg_color,@theme_base_color,0.12)`; disabled →
`mix(@theme_bg_color,@theme_fg_color,0.08)` fill. **Switches:** trough
`shade(@theme_bg_color,0.82)`, checked fill `@theme_selected_bg_color`,
slider `@theme_base_color` (from `spaced-overrides.css`).

The checkmark/radio-dot glyphs are the hicolor fallback SVGs:
`overlays/usr/share/icons/hicolor/scalable/actions/{object-select-symbolic,
list-remove-symbolic,media-record-symbolic}.svg` (16×16, color-class
`currentColor`; default palette classes `#444444` Text / `#4285f4` Highlight
/ `#ff9800` NeutralText / `#4caf50` PositiveText / `#f44336` NegativeText).
GTK recolors them at render time with the CSS `color:` of the node.

---

## 5. GTK 2 colors (`gtk-2.0/gtkrc`)

Every theme: a one-line `gtk-color-scheme` + `include
"/usr/share/themes/Spaced-Dark/gtk-2.0/gtkrc-shared"`, which maps the named
colors onto `bg[NORMAL/ACTIVE/PRELIGHT/SELECTED/INSENSITIVE]`, `fg[...]`,
`base[...]`, `text[...]` with `shade()`/`mix()` factors and styles
`widget_class "*Panel*"`. Scheme order: bg, fg, base, text, selected_bg,
selected_fg, panel_bg, panel_fg.

| Theme | gtk-color-scheme |
|---|---|
| Spaced-Dark | `#383838/#dedede/#333333/#eeeeee/#5588ee/#ffffff/#383838/#dedede` |
| Spaced-Linux-Dark | `#2f2f2f/#dedede/#272727/#eeeeee/#707070/#ffffff/#2f2f2f/#dedede` |
| Spaced-Linux-Light | `#f3f3f3/#1f1f1f/#ffffff/#1f1f1f/#666666/#ffffff/#e6e6e6/#1f1f1f` |
| Spaced-Android | `#263238/#e0e0e0/#20292d/#f0f0f0/#82bbc4/#ffffff/#263238/#ffffff` |
| Spaced-Geoworks | `#d6d6c6/#101010/#f2f2e8/#000000/#006f70/#ffffff/#004040/#ffffff` |
| Spaced-MacOS | `#f5f5f7/#1d1d1f/#ffffff/#1d1d1f/#007aff/#ffffff/#e9e9ec/#1d1d1f` |
| Spaced-Mint | `#2b2b2b/#dedede/#1d1d1d/#f0f0f0/#86a650/#ffffff/#303030/#dedede` |
| Spaced-Win11-Dark | `#17243b/#f3f3f3/#111827/#ffffff/#60cdff/#000000/#17243b/#f3f3f3` |
| Spaced-Win11-Light | `#f3f3f3/#1f1f1f/#ffffff/#1f1f1f/#005fb8/#ffffff/#e6e6e6/#1f1f1f` |
| Spaced-Win311 | `#c0c0c0/#000000/#ffffff/#000000/#000080/#ffffff/#000080/#ffffff` |
| Spaced-WinXP | `#ece9d8/#000000/#ffffff/#000000/#316ac5/#ffffff/#245edb/#ffffff` |

Differences to note: Win311 GTK2 `base_color` is `#ffffff` while GTK3 base
is `#c0c0c0`; Android GTK2 panel fg is `#ffffff` vs GTK3 `#e0e0e0`.

---

## 6. Window decorations (marco/metacity + Compiz)

- **Who draws frames:** Compiz's `decoration` plugin asks the external
  **gtk-window-decorator** (`spaced-window-manager`), which on MATE reads the
  marco theme named by `org.mate.Marco.general theme`. In cairo/builtin mode
  (`use-marco-theme=false`) it instead fills frames from the live GTK style
  colors — either way the colors originate in the GTK theme below.
- **Files:** `metacity-1/metacity-theme-1.xml` (428 lines) and
  `metacity-theme-3.xml` (1,169 lines), derived from **Greybird** (Satyajit
  Sahoo), with per-theme `<name>`. Also `index.theme` (type
  `X-Metacity-Themes`) and button PNGs/SVGs.
- **Colors:** the `theme-3.xml` pulls the GTK palette via
  `gtk:custom(wm_*)` bindings, i.e. the `wm_bg`, `wm_title_focused`,
  `wm_title_unfocused`, `wm_border_focused`, `wm_border_unfocused`
  `@define-color`s from §3 — so titlebar/border colors follow each theme's
  gtk.css automatically. `theme-1.xml` hardcodes title-button gradients
  `#484848→#303030`, glyph `#f4f4f4`, text `#111111`, focused `#202020`,
  unfocused `#aaaaaa`.
- **Compiz decoration plugin options** (shadows etc.): GSettings
  `org.compiz.gwd` keys, shadows under
  `/org/compiz/profiles/<Profile>/plugins/decor/allscreens/options/`
  (`shadow_color`, opacity, radius, offsets), read at runtime over D-Bus.
- **Compiz cube/skydome** (from skel user config
  `etc/skel/.config/compiz/compizconfig/Default.ini`): cube bg `#000000`,
  skydome gradient `#000000ff` → `#00194aff`.

---

## 7. MATE metathemes — `index.theme` pairing

The 10 user themes have a top-level `X-GNOME-Metatheme` `index.theme`
declaring `GtkTheme=Spaced-<N>`, `MetacityTheme=Spaced-<N>`,
`IconTheme=Spaced-Icons-<N>`, `CursorTheme=Adwaita`,
`BackgroundImage=…/spaced/<wallpaper>`, `BackgroundColor=<hex>`. The
BackgroundColor acts as the wallpaper-fallback solid color:

| Theme | BackgroundColor | Theme | BackgroundColor |
|---|---|---|---|
| Spaced-Linux-Dark | `#1a1a1a` | Spaced-Win11-Light | `#e8eef7` |
| Spaced-Linux-Light | `#f0f0f0` | Spaced-Win11-Dark | `#202020` |
| Spaced-Android | `#303030` | Spaced-Win311 | `#008080` |
| Spaced-Geoworks | `#d6d6c6` | Spaced-WinXP | `#6b8e3f` |
| Spaced-MacOS | `#dce8f5` | Spaced-Mint | `#1d1d1d` |

Spaced-Dark deliberately ships **no** top-level metatheme `index.theme`
(enforced by `scripts/check.sh`) so the engine-only theme isn't exposed as
a duplicate selectable theme.

---

## 8. Panel colors — three independent channels

1. **GTK CSS** (`spaced-overrides.css` + each theme's `gtk.css` tail):
   `.mate-panel`, `.mate-panel-menu-bar`, `#MatePanelWidget`,
   `#PanelApplet`, `#showdesktop-button` → `@panel_bg_color` /
   `@panel_fg_color` (per-theme table in §3). Win11-Dark overrides hover
   `alpha(#ffffff,0.10)` and checked `alpha(#ffffff,0.08)` + `inset 0 -2px
   @theme_selected_bg_color` (flat taskbar look). WinXP overrides with the
   Luna blue gradient taskbar `#3b80f7→#245edb 48%→#1941a5` and green
   Start button `#6cbd55→#3c9a3c→#28772d` (border `#1f6b25`).
2. **Toplevel background** (`spaced-switch-theme` writes
   `org.mate.panel.toplevels.{bottom,top}/background/`): `type 'color'` +
   `color <panel_color>` + `opacity 65535` when `themes.json` has
   `panel_color` (`#2f2f2f` linux-dark, `#17243b` win11-dark, `#263238`
   android); otherwise `type 'none'` (CSS colors show through). This
   channel is painted by mate-panel itself (not CSS) and adds class
   `.mate-custom-panel-background`.
3. **GTK2** — `panel_bg_color`/`panel_fg_color` in each `gtkrc` for the
   `widget_class "*Panel*"` style (Legacy apps only).

Widget-applet transparency requires the Compiz `composite` plugin; without
a compositor alpha is forced opaque.

---

## 9. Icon themes — `overlays/usr/share/icons/`

Registries: 11 `Spaced-Icons-*` sets + 2 menu sets + `hicolor`. Selection is
MATE's metatheme mapping `IconTheme=Spaced-Icons-<N>` (§7); the gschema
override pins `Spaced-Icons-Linux-Dark` by default.

### Folder (places) colors — standalone flat SVGs

Each `Spaced-Icons-<N>/scalable/places/` owns `folder.svg`,
`user-desktop.svg`, `user-home.svg`, `user-home-open.svg` (Papirus
silhouette, 64×64, flat fill + `#fff` 18% sheen). **No symlink swapping —
the old Papirus `folder-<color>.svg` repointing no longer exists.**

| Icon theme | folder fill | Icon theme | folder fill |
|---|---|---|---|
| Spaced-Icons-Spaced-Dark | `#777777` | Spaced-Icons-Win11-Dark | `#3979c9` |
| Spaced-Icons-Linux-Dark | `#8e8e8e` | Spaced-Icons-Win11-Light | `#5294e2` |
| Spaced-Icons-Linux-Light | `#aab2bd` | Spaced-Icons-Win311 | `#d2aa45` |
| Spaced-Icons-MacOS | `#4a90e2` | Spaced-Icons-Geoworks | `#607d8b` |
| Spaced-Icons-Android | `#26a69a` | Spaced-Icons-Mint | `#86a650` |
| Spaced-Icons-WinXP | `#d6b35a` (+ `#f3dc91` two-tone fill) | | |

Only Linux-Dark (17 SVGs) and Linux-Light (16) add extras:
`scalable/apps/multimedia-volume-control.svg` (`#3f3f3f/#4f4f4f` +
`#fec006` speaker), `scalable/devices/drive-harddisk.svg`,
`drive-optical.svg`, `media-cdrom.svg`, `media-optical*.svg` (gray family
`#31363b…#e2e5e9`), `audio-volume-*.svg` (`#e4e4e4`). All other themes
fall back to Papirus for these. `index.theme` inheritance:
`Spaced-Menu-On-{Dark|Light}, Papirus-Dark, hicolor`.

### Menu/panel icons (`Spaced-Menu-On-Dark` / `-Light`)

| Icon | Dark fill | Light fill |
|---|---|---|
| `start-here.svg` / `-symbolic` | `#f3f3f3` | `#202020` |
| `user-trash.svg` / `user-trash-full.svg` | `#6b7280`/`#e5e7eb` | `#111827`/`#4b5563`/`#6b7280` |

### Brand / misc (hicolor)

`hicolor/scalable/apps/spaced-linux-menu.svg` (blue S mark `#5588ee` +
`#ffffff`), `install-spaced-linux.svg` (`#9a9a9a`/`#ffffff`),
`hicolor/{48x48,256x256}/apps/*.png`, `pixmaps/spaced-logo.png`,
`pixmaps/faces/spaced-linux.png`; repo `branding/` adds
`spaced-mark-{black,dark-gray,light-gray,white}.png`.

---

## 10. Wallpapers & solid fallback colors

Deployed in `overlays/usr/share/backgrounds/spaced/` (source art in
`SpacedLinuxWallpapers/`), registered in
`usr/share/mate-background-properties/spaced-linux.xml` whose `pcolor`
defines the solid fallback color:

| File | Fallback | File | Fallback |
|---|---|---|---|
| SpacedBack (jpg/png) | `#1a1a1a` | macos.jpg | `#3a3a3a` |
| Spaced Back Light | `#f0f0f0` | winxp.jpg | `#235edc` |
| SimpleBackb (LDM/GRUB) | `#17181d` | win311.jpg | `#808080` |
| spaced-orbit-4k | `#050912` | win11light.jpg | `#f3f3f3` |
| linuxmint.jpg | `#1d1d1d` | win11dark.jpg | `#0d1430` |
| geoworks.jpg | `#404040` | android.jpg | `#303030` |
| bluecanvas.jpg | `#1a3a5c` | euclid / solarsystem | `#0a0a1a` / `#1a1a2e` |

Default desktop background (`90_…gschema.override`): `picture-filename
=/usr/share/backgrounds/spaced/SpacedBack.jpg`, `picture-options='zoom'`,
solid `primary-color='#1a1a1a'` on both `org.mate.background` and
`org.gnome.desktop.background`. Painted by mate-settings-daemon's background
plugin (MATE is the sole wallpaper owner; required `active=true`).

---

## 11. Cairo-Dock

- No custom dock theme is shipped: the upstream **`Default-Single`** theme
  from `cairo-dock-core` is copied to `~/.config/cairo-dock/current_theme/`.
  Its applet `.conf` files (`[Colours]` sections) can set fills/text/frame
  colors; left at defaults, cairo-dock picks colors from the current GTK
  theme. Dock widgets receive `Net/ThemeName`/`Net/IconThemeName` via
  XSETTINGS like any GTK app.
- Spaced launchers (no colors): `usr/share/spaced-themes/cairo-dock/launchers/
  {01-files,02-terminal,03-calculator,04-install}.desktop`.
- `spaced-switch-theme` seeds the config, strips `modules=`/`visibility=1`
  and launches `cairo-dock -c -f -a -d` (software GL backend for QEMU).
- Compiz integration colors from skel `Default.ini` — see §6.

---

## 12. Cross-toolkit & app-level colors

| Target | Mechanism | Values |
|---|---|---|
| MATE Terminal | gsettings forced on every theme switch (`spaced-switch-theme`) | dark: bg `#000000` fg `#888888`; light: bg `#ffffff` fg `#000000`; `use-theme-colors=false`; palette `#000000:#cc0000:#4e9a06:#c4a000:#3465a4:#75507b:#06989a:#d3d7cf:#555753:#ef2929:#8ae234:#fce94f:#729fcf:#ad7fa8:#34e2e2:#eeeeee`; bold `#ffffff` |
| Qt apps | `QT_QPA_PLATFORMTHEME=gtk3` (profile.d) so Qt draws with GTK theme colors; plus `etc/xdg/QtProject/qtquickcontrols2.conf` `[Universal] Theme=Dark Accent=#cfd3d8` | follows GTK elsewhere |
| LibreOffice | `SAL_USE_VCLPLUGIN=gtk3` | follows GTK |
| Toolkit dark pref | `org.gnome.desktop.interface color-scheme` set to `prefer-dark`/`default` per `dark:` in themes.json | dark themes: linux-dark, mint, win11-dark, android |
| Brisk menu | `com.solus-project.brisk-menu dark-theme` per theme | same dark set |
| GTK2 legacy | XSETTINGS `Gtk/ColorScheme` (from `org.mate.interface gtk-color-scheme`) | gtkrc named colors (§5) |

---

## 13. Flatpak propagation

`spaced-switch-theme` exports every `/usr/share/themes/Spaced-*` (real
copies, `rsync -a --delete`) into `~/.local/share/themes`, grants
`flatpak override --user --filesystem=xdg-data/themes:ro`, and sets
`--env="GTK_THEME=<theme>"` so sandboxed GTK apps resolve the theme files
and render with the active palette.

---

## 14. LightDM greeter colors

`overlays/etc/lightdm/lightdm-gtk-greeter.conf`: background
`SimpleBackb.png`, **`theme-name=Spaced-Dark`**, **`icon-theme-name=
Papirus-Dark`**, default user image `spaced-linux.png`, logo
`pixmaps/spaced-logo.png`.

---

## 15. gsettings defaults carrying colors

`overlays/usr/share/glib-2.0/schemas/90_spaced-linux.gschema.override`
(color-relevant keys):

```ini
[org.mate.interface]                 gtk-theme='Spaced-Linux-Dark'  icon-theme='Spaced-Icons-Linux-Dark'
[org.gnome.desktop.interface]        gtk-theme / icon-theme (same)  color-scheme='prefer-dark'
[org.mate.Marco.general]             theme='Spaced-Linux-Dark'
[org.mate.background]                picture-filename=SpacedBack.jpg  picture-options='zoom'
                                     color-shading-type='solid'  primary-color='#1a1a1a'
[org.gnome.desktop.background]       picture-uri=file:///…/SpacedBack.jpg  primary-color='#1a1a1a'
[org.mate.panel]                     default-layout='spaced-linux'
[org.mate.terminal.profile:/…/default]  bg='#000000' fg='#888888' bold='#ffffff' + palette (above)
```

Compiz schemas are `org.compiz.*` (relocatable, installed by compiz
packages); user values live under dconf
`/org/compiz/profiles/<Profile>/plugins/…` (skel `Default.ini` sets the
cube/skydome colors in §6).

---

## 16. Quick reference — "I want to change X → edit Y"

| I want to change | File (all under `overlays/`) |
|---|---|
| Any theme's core colors | `usr/share/themes/Spaced-<N>/gtk-3.0/gtk.css` (`@define-color` block) |
| Check/radio colors | same file's tail rule (§4 table) |
| Unchecked control shape/glyph | `usr/share/themes/Spaced-Dark/gtk-3.0/gtk-widgets-assets.css` |
| Widget rules (buttons, entries…) | `…/Spaced-Dark/gtk-3.0/gtk-widgets.css` |
| Inactive-window state | `…/Spaced-Dark/gtk-3.0/gtk-widgets-backdrop.css` |
| Panel color per theme | `themes.json` `panel_color` (or gtk.css `@panel_bg_color`) |
| Titlebar/frame colors | gtk.css `wm_*` values (decorator binds via `gtk:custom`) |
| Folder icon colors | `usr/share/icons/Spaced-Icons-<N>/scalable/places/folder.svg` etc. |
| Start menu / trash icons | `usr/share/icons/Spaced-Menu-On-{Dark,Light}/scalable/places/` |
| Checkmark glyph SVGs | `usr/share/icons/hicolor/scalable/actions/{object-select,list-remove,media-record}-symbolic.svg` |
| Wallpaper + fallback color | `usr/share/backgrounds/spaced/` + `usr/share/mate-background-properties/spaced-linux.xml` |
| Terminal colors | `90_spaced-linux.gschema.override` (and per-theme switch logic in `usr/local/bin/spaced-switch-theme`) |
| Dock colors | `~/.config/cairo-dock/current_theme/` applet configs (Default-Single base) |
| Compiz colors | dconf `/org/compiz/profiles/Default/plugins/…` (skel: `etc/skel/.config/compiz/compizconfig/Default.ini`) |
| Qt quick controls | `etc/xdg/QtProject/qtquickcontrols2.conf` (`Accent=#cfd3d8`) |
| Greeter | `etc/lightdm/lightdm-gtk-greeter.conf` |
| What a theme selects end-to-end | `usr/share/spaced-themes/themes.json` + `usr/local/bin/spaced-switch-theme` |

---

## 17. Known discrepancies (dated documentation)

- `THEMES-REFERENCE.md` at the repo root is **stale**: it describes
  `spaced-theme-watch`/`spaced-init-session`, a 2 s polling watcher, a
  `folder_color` key, and root-level Papirus `folder-<color>.svg` symlink
  swapping. None of these exist in the current code. Current: monitor-based
  `spaced-theme-monitor`, `panel_color` in themes.json, standalone
  `Spaced-Icons-*` SVGs.
- `build/live-build/chroot/usr/share/…` mirrors stale theme files (missing
  the 2026-08-12 check/radio commits) — it is a build artifact, not a
  source.
- Windows paths check: GTK3 theme dir case-matching is exact on disk; MATE
  lowercases `gtk-theme` values it stores (`Spaced-WinXP` → `Spaced-Winxp`),
  which `spaced-theme-monitor` matches case-insensitively.
- The 4 "self-contained" check/radio themes (§4, style 2) use a different
  CSS shape than the 7 refined themes (style 1). Functionally identical
  colors; shape divergence is intentional only for Win311 (radius 0).