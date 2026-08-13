# Spaced Linux MATE theme architecture

This is the canonical contributor guide for Spaced Linux theming. It describes the repository at commit `f462bdb4b4d3916caf1617159056f2743b016acf`; re-check the implementation when later commits change theme files or session helpers.

For exact color values, see [THEME-COLORS.md](THEME-COLORS.md). For panel objects and layout details, see [matepanel.md](matepanel.md).

## Theme inventory

Spaced Linux ships **ten selectable MATE metathemes** and one internal shared engine directory:

- `Spaced-Linux-Dark`
- `Spaced-Linux-Light`
- `Spaced-MacOS`
- `Spaced-Win311`
- `Spaced-WinXP`
- `Spaced-Mint`
- `Spaced-Win11-Light`
- `Spaced-Win11-Dark`
- `Spaced-Geoworks`
- `Spaced-Android`
- `Spaced-Dark` — internal GTK/Metacity engine used by the other themes; intentionally not exposed as a selectable top-level MATE metatheme.

The similar names are important:

- **Spaced Linux Dark** is the selectable default desktop theme in `Spaced-Linux-Dark`.
- **Spaced-Dark** is the internal engine and LightDM theme. It has no top-level `X-GNOME-Metatheme` file.

`make check` enforces ten registered/selectable themes and rejects `Spaced-Dark` if it becomes exposed as a duplicate choice.

## Repository paths and installed paths

The `overlays/` tree is copied onto the target filesystem. Remove the leading `overlays/` to get the installed path:

```text
overlays/usr/share/themes/...       -> /usr/share/themes/...
overlays/usr/share/icons/...        -> /usr/share/icons/...
overlays/usr/local/bin/...          -> /usr/local/bin/...
overlays/etc/xdg/...                -> /etc/xdg/...
overlays/etc/skel/...               -> /etc/skel/...
```

`/etc/skel` seeds newly created home directories. It does not imply that every installed account is named `user`; `user` is the live-session account.

The important source-of-truth locations are:

| Area | Repository path |
|---|---|
| GTK2, GTK3, Metacity/Marco themes, static previews | `overlays/usr/share/themes/Spaced-*` |
| Per-theme icon overlays | `overlays/usr/share/icons/Spaced-Icons-*` |
| Shared menu/panel icon overlays | `overlays/usr/share/icons/Spaced-Menu-On-{Dark,Light}` |
| Fallback symbolic indicator glyphs | `overlays/usr/share/icons/hicolor/scalable/actions/` |
| Coordinated runtime extras | `overlays/usr/share/spaced-themes/themes.json` |
| Theme-change monitor | `overlays/usr/local/bin/spaced-theme-monitor` |
| Runtime extras helper | `overlays/usr/local/bin/spaced-switch-theme` |
| Default desktop settings | `overlays/usr/share/glib-2.0/schemas/90_spaced-linux.gschema.override` |
| Panel layouts | `overlays/usr/share/mate-panel/layouts/` |
| Wallpapers | `overlays/usr/share/backgrounds/spaced/` |
| Wallpaper catalog and fallback colors | `overlays/usr/share/mate-background-properties/spaced-linux.xml` |
| Compiz profile seed | `overlays/etc/skel/.config/compiz/compizconfig/` |
| Cross-toolkit environment | `overlays/etc/profile.d/spaced-application-theming.sh` |
| Qt Quick Controls policy | `overlays/etc/xdg/QtProject/qtquickcontrols2.conf` |

Do not edit `build/live-build/chroot/` as source. It is a generated build tree and may contain stale copies.

## What a MATE metatheme owns

Each selectable theme directory contains a top-level `index.theme` with `Type=X-GNOME-Metatheme`. It pairs:

- a GTK theme;
- a Metacity/Marco window-decoration theme;
- a `Spaced-Icons-*` icon theme;
- the Adwaita cursor theme;
- a suggested wallpaper and fallback background color.

Each selectable directory also contains:

```text
gtk-2.0/gtkrc
gtk-3.0/gtk.css
gtk-3.0/index.theme
metacity-1/index.theme
metacity-1/metacity-theme-1.xml
metacity-1/metacity-theme-3.xml
preview.png
```

`Spaced-Dark` contains the shared GTK2/GTK3 engine, Metacity assets, and a preview, but no top-level selectable metatheme metadata.

## Runtime flow

### 1. MATE applies the metatheme components

When a user chooses a theme in Appearance Preferences, MATE writes the component settings, principally:

```text
org.mate.interface gtk-theme
org.mate.interface icon-theme
org.mate.Marco.general theme
org.mate.background picture-filename
```

`mate-settings-daemon` publishes the GTK and icon choices through XSettings so normal GTK applications can follow the session.

### 2. `spaced-theme-monitor` watches the GTK theme

The system-wide autostart file is:

```text
/etc/xdg/autostart/spaced-theme-monitor.desktop
```

It starts `/usr/local/bin/spaced-theme-monitor`. The monitor:

- creates a single-instance lock in `XDG_RUNTIME_DIR`;
- restores saved visual choices from `~/.config/spaced/` at login;
- monitors GTK, icon, window-theme, and wallpaper settings through `gsettings monitor`;
- maps the current GTK theme to an entry in `themes.json`;
- invokes `spaced-switch-theme <id>` for registered Spaced themes;
- saves the current GTK theme, icon theme, window theme, and wallpaper as a small fallback for newly installed accounts whose last dconf writes may not survive the first reboot.

The current lookup is an **exact, case-sensitive comparison**:

```python
if t.get("gtk_theme") == gtk:
```

Therefore `org.mate.interface gtk-theme` must exactly match the `gtk_theme` value in `themes.json`. Do not rely on case normalization.

At login the monitor restores GTK, icon, and window-theme choices, applies the registered theme extras, and then restores the saved wallpaper. This order preserves a user-selected custom wallpaper instead of replacing it permanently with the metatheme suggestion.

### 3. `spaced-switch-theme` applies coordinated extras

The helper deliberately does not rewrite the GTK, icon, or Marco keys. MATE has already selected those components, and rewriting them would make Appearance Preferences fall back to “Custom.”

For a registered theme, the helper applies:

- the suggested MATE wallpaper and `zoom` mode;
- Brisk Menu's dark-theme preference;
- `org.gnome.desktop.interface color-scheme` as `prefer-dark` or `default`;
- MATE Terminal background and foreground colors;
- panel layout name, edge, size, and optional explicit toplevel background color;
- Cairo Dock start or stop;
- real copies of all `Spaced-*` theme directories into `~/.local/share/themes` for Flatpak access;
- the per-user Flatpak theme filesystem permission and `GTK_THEME` override.

### External GTK themes

Only themes registered in `themes.json` receive coordinated Spaced extras. If a user selects an external GTK theme, the monitor finds no Spaced theme ID and does not run the switch helper.

That means panel position, explicit panel color, terminal colors, or Cairo Dock state left by the previous Spaced theme may remain. This is current behavior, not a promise that external themes are normalized automatically.

## `themes.json`

`overlays/usr/share/spaced-themes/themes.json` contains ten entries. Current keys are:

| Key | Purpose |
|---|---|
| `id` | Stable argument accepted by `spaced-switch-theme` |
| `name` | Human-readable log/display name |
| `gtk_theme` | Exact GTK theme name used for monitor lookup |
| `wallpaper` | Installed wallpaper path |
| `panel_layout` | MATE panel layout name |
| `panel_position` | `top` or `bottom` |
| `panel_size` | Panel height in pixels |
| `panel_color` | Optional explicit MATE toplevel background color |
| `cairo_dock` | Whether Cairo Dock should run |
| `dark` | Brisk, toolkit dark preference, and terminal light/dark policy |

There is no current `folder_color`, `icon_theme`, or `cairo_dock_position` key. Folder colors come from the metatheme's icon-theme selection, not from runtime Papirus rewriting.

Current registry:

| ID | GTK theme | Icon theme | Wallpaper | Panel | Explicit panel color | Dock | Dark |
|---|---|---|---|---|---|---|---|
| `linux-dark` | `Spaced-Linux-Dark` | `Spaced-Icons-Linux-Dark` | `SpacedBack.jpg` | bottom, 30 | `#2f2f2f` | no | yes |
| `linux-light` | `Spaced-Linux-Light` | `Spaced-Icons-Linux-Light` | `SpacedBackLight.jpg` | bottom, 30 | none | no | no |
| `macos` | `Spaced-MacOS` | `Spaced-Icons-MacOS` | `macos.jpg` | top, 30 | none | yes | no |
| `win311` | `Spaced-Win311` | `Spaced-Icons-Win311` | `win311.jpg` | bottom, 30 | none | no | no |
| `winxp` | `Spaced-WinXP` | `Spaced-Icons-WinXP` | `winxp.jpg` | bottom, 30 | none | no | no |
| `mint` | `Spaced-Mint` | `Spaced-Icons-Mint` | `linuxmint.jpg` | bottom, 30 | none | no | yes |
| `win11-light` | `Spaced-Win11-Light` | `Spaced-Icons-Win11-Light` | `win11light.jpg` | bottom, 30 | none | no | no |
| `win11-dark` | `Spaced-Win11-Dark` | `Spaced-Icons-Win11-Dark` | `win11dark.jpg` | bottom, 30 | `#17243b` | no | yes |
| `geoworks` | `Spaced-Geoworks` | `Spaced-Icons-Geoworks` | `geoworks.jpg` | bottom, 30 | none | no | no |
| `android` | `Spaced-Android` | `Spaced-Icons-Android` | `android.jpg` | top, 30 | `#263238` | yes | yes |

The icon-theme column comes from each top-level metatheme `index.theme`, not from `themes.json`.

## GTK3 architecture

### Theme discovery

GTK3 searches for the current theme's CSS in this order:

1. `$XDG_DATA_HOME/themes/<theme>/gtk-3.x/gtk.css`, normally `~/.local/share/themes`;
2. `~/.themes/<theme>/gtk-3.x/gtk.css`;
3. each `$XDG_DATA_DIRS/themes/<theme>/gtk-3.x/gtk.css` location;
4. GTK's compiled default theme directory.

It tries the current compatible GTK3 version and then older even-numbered theme directories down to `gtk-3.0`. Spaced themes keep their CSS in `gtk-3.0/`.

A user file at `~/.config/gtk-3.0/gtk.css` is a higher-priority user style provider and can override theme rules. Check it whenever an installed theme file appears correct but a widget still renders differently.

`GTK_THEME=<name>` overrides the selected theme for a process. It is a theme-selection override, not a universal override for every `GtkSettings` property.

### Shared engine

`Spaced-Dark/gtk-3.0/` owns the shared engine:

| File | Role |
|---|---|
| `gtk-widgets.css` | General widgets, selections, entries, buttons, menus, scrollbars, notebooks, trees, and application surfaces |
| `gtk-widgets-assets.css` | Check-box and radio-button shapes, states, fallback glyph names, and fallback-image resets |
| `gtk-widgets-backdrop.css` | Inactive-window/backdrop states |
| `spaced-overrides.css` | Modern cross-theme fixes for buttons, switches, toolbars, panels, Caja, and related surfaces |
| `apps/*.css` | Application-specific compatibility rules |
| `gtk.css` | Internal engine palette and its own tail overrides |

Every selectable theme defines its palette first, imports those shared files with relative paths, and then appends its theme-specific rules. Because the per-theme rules occur after the imports, they win when selector specificity is otherwise equal.

The imports are relative so copied themes continue to work in Flatpak exports or unpacked test locations. Do not replace them with absolute `/usr/share/themes/...` imports.

### Palette ownership

Each theme's `gtk-3.0/gtk.css` defines semantic colors such as:

```css
@define-color theme_bg_color ...;
@define-color theme_fg_color ...;
@define-color theme_base_color ...;
@define-color theme_text_color ...;
@define-color theme_selected_bg_color ...;
@define-color theme_selected_fg_color ...;
@define-color panel_bg_color ...;
@define-color panel_fg_color ...;
@define-color wm_bg ...;
@define-color wm_title_focused ...;
@define-color wm_title_unfocused ...;
@define-color wm_border_focused ...;
@define-color wm_border_unfocused ...;
```

Shared rules should use semantic variables whenever possible. Theme-specific emulation rules may use literal colors when an original operating system requires a distinct treatment.

### Check boxes and radio buttons

GTK3 renders these controls through `check` and `radio` CSS subnodes. The shared asset file supplies:

- 14 px minimum indicator size;
- a 2 px-radius checkbox and circular radio button;
- unchecked fill and border from the current palette;
- symbolic glyph names for checked, indeterminate, and selected-radio states;
- `background-image: none`, `-gtk-icon-source: none`, and `-gtk-icon-shadow: none` resets before state-specific glyphs are added.

The `background-image: none` reset is essential. Without it, GTK's fallback theme can paint a blue gradient over a per-theme `background-color`, making the CSS color appear ineffective.

Per-theme tail rules choose the checked fill, border, and glyph color. Windows 3.11 deliberately makes check boxes square while radios remain circular.

### Static preview images

Each theme directory currently ships `preview.png`. This is a static Appearance Preferences card and is independent of live GTK CSS.

Changing `gtk.css`, `gtk-widgets-assets.css`, icons, or window decorations does **not** edit `preview.png`. After a visual change, verify both:

1. a newly launched live GTK application;
2. the committed preview image.

Regenerate or replace the preview separately when the card should reflect the new appearance.

## GTK2

Each theme owns `gtk-2.0/gtkrc`. It defines a `gtk-color-scheme` and includes:

```text
/usr/share/themes/Spaced-Dark/gtk-2.0/gtkrc-shared
```

The per-theme `gtkrc` is the normal source of GTK2 colors. The current GSettings defaults and switch helper do not set `org.mate.interface gtk-color-scheme` as part of theme switching.

GTK2 and GTK3 palettes are maintained separately and can diverge. Test a legacy GTK2 application when changing a color that is expected to match both toolkits.

## Window decorations and Compiz

MATE starts `/usr/local/bin/spaced-window-manager` as the required window manager. That script:

- checks that an X display and direct-rendering GLX context are available;
- starts `compiz ccp --replace`;
- restarts Compiz after a crash while X is still alive;
- does not paint the wallpaper and does not act as the window decorator.

The Compiz INI profile is seeded from:

```text
overlays/etc/skel/.config/compiz/compizconfig/Default.ini
```

and becomes:

```text
~/.config/compiz/compizconfig/Default.ini
```

The companion `config` file selects the INI backend and MATE integration.

Compiz's `decoration` plugin separately starts:

```text
gtk-window-decorator --replace
```

The selected window theme is stored in `org.mate.Marco.general theme`. Each selectable theme provides `metacity-1/metacity-theme-1.xml` and `metacity-theme-3.xml`. The version-3 files consume `wm_*` values from the active GTK palette through `gtk:custom(...)` bindings.

The Compiz profile also owns independent presentation colors such as the cube background and skydome gradient. Those values do not come from `gtk.css`.

## Icon themes

Each selectable metatheme names a separate `Spaced-Icons-*` overlay. These overlays own their themed folder/home icons and inherit the rest of the icon set from `Spaced-Menu-On-Dark` or `Spaced-Menu-On-Light`, Papirus Dark, and finally hicolor.

No theme switch rewrites root-owned Papirus symlinks. Folder color is fixed by the selected icon overlay.

Linux Dark and Linux Light also carry additional volume, drive, and optical-media icons. Do not describe every `Spaced-Icons-*` directory as folder-only.

The shared GTK control CSS asks the icon theme for these symbolic names:

```text
object-select-symbolic
list-remove-symbolic
media-record-symbolic
```

Spaced ships hicolor fallback SVGs for them. GTK resolves each name through the active icon theme's inheritance chain, so a higher-priority inherited theme can provide the final asset. Symbolic results are recolored from the control node's CSS `color`.

After installing icon changes, refresh caches with `gtk-update-icon-cache` or reinstall the desktop defaults package; its post-install script refreshes each `Spaced-*` icon theme.

## Wallpapers

MATE's settings daemon is the sole wallpaper painter. The background plugin is enabled through the GSettings override.

Wallpaper sources:

- image files: `overlays/usr/share/backgrounds/spaced/`;
- catalog and solid fallbacks: `overlays/usr/share/mate-background-properties/spaced-linux.xml`;
- metatheme suggestion: each selectable theme's top-level `index.theme`;
- coordinated runtime suggestion: `themes.json` and `spaced-switch-theme`;
- user persistence: `spaced-theme-monitor` saves and restores the selected filename.

Do not use `feh`, Caja restarts, Compiz background options, or repeated background-plugin toggles as part of normal theme switching.

## Panel and Cairo Dock

All ten selectable themes use one applet composition. Nine layout files exist because Linux Dark and Linux Light both use `spaced-linux.layout`; the macOS and Android files set the initial top orientation, while the other files use bottom orientation.

At runtime `spaced-switch-theme` moves and resizes the existing panel. It never runs `mate-panel --replace`, because replacing the panel can lose the notification-area X selection.

Panel color has two GTK3-era channels:

1. GTK CSS paints panel widgets using `@panel_bg_color` and `@panel_fg_color`.
2. An optional `themes.json` `panel_color` makes mate-panel paint an explicit toplevel background.

The explicit toplevel color can cover the CSS background while widget text and controls still come from CSS. See [matepanel.md](matepanel.md) for the complete model.

Cairo Dock is enabled only for macOS and Android. The helper seeds the upstream `Default-Single` theme on first use, replaces launchers with the Spaced set, and launches the software backend used by the project.

## Cross-toolkit applications

`/etc/profile.d/spaced-application-theming.sh` exports:

```bash
SAL_USE_VCLPLUGIN=gtk3
QT_QPA_PLATFORMTHEME=gtk3
```

This asks LibreOffice and Qt Widgets applications to integrate with GTK3.

Qt Quick Controls are separate. The current global file forces:

```ini
[Controls]
Style=Universal

[Universal]
Theme=Dark
Accent=#cfd3d8
```

Therefore Qt Quick applications do not dynamically become light with a light Spaced theme. Do not document all Qt applications as fully following GTK.

GTK4 and libadwaita applications do not consume the Spaced GTK3 CSS engine and are not guaranteed to match.

## Flatpak theme propagation

On each registered theme switch, `spaced-switch-theme`:

1. copies every `/usr/share/themes/Spaced-*` directory into `~/.local/share/themes` with `rsync -a --delete`;
2. grants `xdg-data/themes:ro` to user Flatpaks;
3. sets a per-user Flatpak `GTK_THEME=<active-theme>` environment override.

Real copies are used because symlinks back to `/usr/share/themes` do not survive reliably inside a sandbox namespace.

This supports sandboxed GTK3 applications that permit host themes. It does not guarantee matching GTK4/libadwaita or Qt rendering.

A stale user export can shadow the freshly installed `/usr/share/themes` copy because GTK searches `~/.local/share/themes` first. Re-run a registered theme switch or remove/recreate the export when debugging.

## LightDM

The greeter is intentionally independent of the user's selected metatheme:

```text
background     = /usr/share/backgrounds/spaced/SimpleBackb.png
theme-name     = Spaced-Dark
icon-theme-name= Papirus-Dark
```

Changing a selectable desktop theme does not change the login screen.

## Adding a selectable theme

Update these components together:

1. Create `overlays/usr/share/themes/Spaced-<Name>/` with:
   - top-level `index.theme`;
   - `gtk-2.0/gtkrc`;
   - `gtk-3.0/gtk.css` and `gtk-3.0/index.theme`;
   - `metacity-1/index.theme` and both XML theme versions;
   - `preview.png`.
2. Define the GTK3 semantic palette before the shared imports.
3. Use relative imports from `../../Spaced-Dark/gtk-3.0/`.
4. Add only the theme-specific tail rules needed for OS emulation.
5. Create a matching `Spaced-Icons-<Name>` overlay and point the metatheme to it.
6. Add or select a wallpaper and fallback background color.
7. Add one exact `themes.json` entry.
8. Reuse an existing panel layout unless the initial orientation truly differs.
9. Run `make check`.
10. Test GTK3, GTK2, window decorations, the panel, the preview image, icons, wallpaper, terminal, and Flatpak behavior.

Avoid adding a second complete copy of the shared GTK engine.

## Editing an existing theme

Use this ownership rule:

| Desired change | Edit |
|---|---|
| Theme-wide GTK3 color | that theme's `gtk-3.0/gtk.css` palette |
| Checked control color | that theme's tail rule in `gtk.css` |
| Shared check/radio shape, glyph, unchecked, hover, or disabled state | `Spaced-Dark/gtk-3.0/gtk-widgets-assets.css` |
| Shared switches or modern surface fixes | `Spaced-Dark/gtk-3.0/spaced-overrides.css` |
| General GTK3 widget behavior | `Spaced-Dark/gtk-3.0/gtk-widgets.css` |
| Inactive-window styling | `Spaced-Dark/gtk-3.0/gtk-widgets-backdrop.css` |
| GTK2 palette | that theme's `gtk-2.0/gtkrc` |
| Titlebar/frame palette | `wm_*` values in that theme's GTK3 palette, plus Metacity XML only when geometry or drawing logic changes |
| Folder/home icon color | matching `Spaced-Icons-*` SVGs |
| Preview card | the theme's static `preview.png` |
| Suggested wallpaper or panel/dock behavior | `themes.json` and the top-level metatheme metadata as appropriate |

## Installing documentation or theme changes on a running system

Changing the Git checkout does not update `/usr/share`. Build as the normal user, then install with privilege:

```bash
cd /path/to/spaced
make check
scripts/iso/build-local-packages.sh

version=$(cat VERSION)
sudo dpkg -i "build/local-packages/spaced-mate-default-settings_${version}_all.deb"
```

The package version may be identical to the installed version during local development. A normal APT upgrade will not regard that rebuild as newer, so install the local `.deb` explicitly.

Do not run the build from a root login using `~/spaced`; root's home is `/root`, and root-owned build artifacts can make later normal-user builds troublesome.

After installation:

- close and reopen the application being tested;
- switch to another GTK theme and back, or log out and in;
- remember that preview PNGs and Flatpak exports are separate copies.

Verify the active GTK3 file:

```bash
current=$(gsettings get org.mate.interface gtk-theme | tr -d "'")
repo=/path/to/spaced

cmp -s \
  "$repo/overlays/usr/share/themes/$current/gtk-3.0/gtk.css" \
  "/usr/share/themes/$current/gtk-3.0/gtk.css" \
  && echo "Installed GTK3 theme matches the checkout." \
  || echo "Installed GTK3 theme differs from the checkout."
```

For a shared control-engine change, compare the shared file too:

```bash
cmp -s \
  "$repo/overlays/usr/share/themes/Spaced-Dark/gtk-3.0/gtk-widgets-assets.css" \
  "/usr/share/themes/Spaced-Dark/gtk-3.0/gtk-widgets-assets.css"
```

## Live GTK3 control test

Use a new process so no previous CSS provider is retained:

```bash
current=$(gsettings get org.mate.interface gtk-theme | tr -d "'")

THEME="$current" python3 - <<'PY'
import os
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

settings = Gtk.Settings.get_default()
settings.set_property("gtk-theme-name", os.environ["THEME"])

window = Gtk.Window(title=f"Live GTK3 controls — {os.environ['THEME']}")
window.connect("destroy", Gtk.main_quit)
box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
box.set_border_width(24)

checked = Gtk.CheckButton(label="Checked checkbox")
checked.set_active(True)
unchecked = Gtk.CheckButton(label="Unchecked checkbox")
selected = Gtk.RadioButton.new_with_label_from_widget(None, "Selected radio")
unselected = Gtk.RadioButton.new_with_label_from_widget(selected, "Unselected radio")
selected.set_active(True)

for widget in (checked, unchecked, selected, unselected):
    box.pack_start(widget, False, False, 0)

window.add(box)
window.show_all()
Gtk.main()
PY
```

This tests live GTK3 rendering. It does not test the static Appearance preview.

## Troubleshooting order

When a theme change appears ineffective, check in this order:

1. Confirm the checkout contains the intended change.
2. Confirm the installed `/usr/share/themes` file matches the checkout.
3. Confirm no same-named theme under `~/.local/share/themes` or `~/.themes` shadows it.
4. Inspect `~/.config/gtk-3.0/gtk.css` for user overrides.
5. Start a new GTK3 process.
6. Test the live widget rather than relying on `preview.png`.
7. If only Flatpaks are stale, trigger a registered theme switch so `~/.local/share/themes` is refreshed.
8. If only GTK2 applications are stale, inspect the theme's `gtk-2.0/gtkrc`.
9. If only titlebars are stale, inspect `org.mate.Marco.general theme`, the Metacity XML, and `gtk-window-decorator`.
10. Run `make check` before committing.

## Validation boundaries

Spaced's automated checks validate registered theme count, required files, XML parsing, icon and wallpaper mappings, relative GTK imports, GTK2 shared-engine use, and other project invariants. They do not replace visual testing.

At minimum, visually test:

- normal, hover, focus, active, checked, indeterminate, disabled, and backdrop states;
- light and dark text contrast;
- GTK3 and GTK2 applications;
- window frames and title buttons;
- panel applets and Brisk Menu;
- static previews;
- user-local and Flatpak copies;
- a newly created account seeded from `/etc/skel`.
