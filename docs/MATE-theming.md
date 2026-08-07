# MATE theme architecture

Spaced Linux ships eleven complete MATE metathemes. The MATE Appearance
control center is the only theme chooser; there is no separate Spaced theme
application.

## Theme ownership

Each directory under `overlays/usr/share/themes/Spaced-*` owns:

- its GTK 2 palette;
- its GTK 3 palette and theme metadata;
- its window decoration;
- its top-level MATE metatheme metadata;
- its wallpaper selection; and
- the name of its matching `Spaced-Icons-*` icon overlay.

The large GTK 3 widget engine lives once under `Spaced-Dark/gtk-3.0`.
Individual themes import that engine and keep their own palette files. This
avoids eleven copies of the same CSS without merging the themes' identities.

The icon overlays inherit normal application icons from Papirus Dark and
override only folder/home icons. Folder color is therefore immutable per
theme. Nothing rewrites root-owned Papirus files, clears thumbnail caches, or
restarts Caja.

## Runtime flow

MATE applies GTK, icons, cursor, and wallpaper from the selected
metatheme. `spaced-theme-monitor` listens for actual theme and wallpaper
changes and keeps a small fallback under `~/.config/spaced/`. At login it
restores those user choices before running `spaced-switch-theme`. This protects
newly installed accounts from losing their last dconf writes on the first
reboot. The helper only handles details a metatheme cannot encode: panel
edge/size and whether Cairo Dock is running.

Wallpaper drawing belongs exclusively to MATE's settings daemon. Its fallback
state is updated from dconf change notifications, not polling. No root-pixmap
helper, `draw-background` toggle, or Compiz restart is used.

The existing panel is moved and resized in place. It is never replaced during
a theme change, which preserves the notification-area selection and avoids the
tray-applet crash.

## Compiz

MATE starts `/usr/local/bin/spaced-window-manager` as its window
manager. The script verifies GLX and starts `compiz ccp --replace`.

The Compiz profile is stored at the Compiz 0.8 path:

```text
~/.config/compiz-1/compizconfig/Default.ini
```

It enables CCSM, cube/rotate, Expo, scale, enhanced zoom, and four horizontal
viewports. Wallpaper is not a Compiz command-line option.

## Adding or changing a theme

Update all three sources together:

1. `overlays/usr/share/themes/Spaced-*/`
2. `overlays/usr/share/icons/Spaced-Icons-*/`
3. `overlays/usr/share/spaced-themes/themes.json`

Then run `make check`. The validator rejects missing components, icon themes,
wallpapers, duplicate mappings, and extra `Spaced-*` theme directories.
