# Spaced Linux visual design

Spaced Linux is a familiar, configurable MATE desktop built on Devuan, sysvinit, and Compiz. Its visual system combines a restrained Spaced identity with coordinated themes inspired by recognizable desktop eras.

This document states current design principles. Implementation details are in [MATE-theming.md](MATE-theming.md), [THEME-COLORS.md](THEME-COLORS.md), and [matepanel.md](matepanel.md).

## Product goals

The desktop should be:

- **familiar** — conventional windows, a visible application menu, a task list, a notification area, a clock, and a clear Show Desktop control;
- **coordinated** — GTK, window decorations, icons, wallpaper, panel treatment, terminal readability, and optional dock behavior should move together;
- **readable** — text and control marks must remain legible in normal, hover, focus, active, disabled, and backdrop states;
- **inspectable** — important visual policy remains in version-controlled text, CSS, XML, JSON, schemas, and SVGs;
- **resilient** — a theme change must not restart the panel, break the tray, mutate package-owned Papirus files, or depend on an unavailable external asset;
- **fast** — visual range should not require several competing wallpaper or theme daemons;
- **honest about coverage** — the project themes GTK3/MATE directly, supports GTK2 deliberately, and does not claim complete control over GTK4/libadwaita or every Qt application.

## The Spaced identity

Spaced Linux Dark and Spaced Linux Light are the core identity themes.

Their ordinary chrome and controls should be predominantly monochrome:

- black, white, and neutral grays for windows, controls, titlebars, panels, and selection marks;
- no decorative accent color added merely for novelty;
- strong contrast between selected control faces and their check marks or radio dots;
- consistent circular radio buttons and restrained checkbox geometry.

“Monochrome” does not prohibit functional semantic color where it communicates meaning. Links, warnings, success messages, error messages, application icons, wallpapers, and third-party content can still use color.

## OS-inspired themes

The selectable collection also includes:

- macOS;
- Windows 3.11;
- Windows XP;
- Linux Mint Dark;
- Windows 11 Light;
- Windows 11 Dark;
- GeoWorks;
- Android.

These themes are interpretations, not pixel-perfect reimplementations. They should preserve MATE usability while using the target system's recognizable visual vocabulary.

### Color policy

Use an accent when it is central to the source system:

- macOS Aqua blue;
- Windows 3.11 navy and classic system gray;
- Windows XP Luna blue and Start-button green;
- Mint-Y Dark green;
- Windows 11 light/dark blue accents;
- GeoWorks dark cyan;
- Android Material teal.

Prefer the source system's functional use of color over broad recoloring. An accent should identify selection, activity, or a distinctive component rather than flooding every surface.

### Structural policy

MATE's widget and panel structure remains authoritative. A theme may alter:

- color;
- border shape;
- gradients;
- shadows;
- selected-tab indicators;
- panel button treatment;
- window-decoration geometry and artwork;
- icon and wallpaper choices.

A theme should not require replacing the panel process, rewriting root-owned upstream assets, or maintaining a separate desktop shell.

## Controls

Check boxes and radio buttons are first-class theme elements.

Requirements:

- checked, unchecked, indeterminate, hover, disabled, and backdrop states must be deliberate;
- live GTK controls, not only static preview cards, must be tested;
- a checkbox mark or radio dot must have sufficient contrast with its face;
- radio buttons remain circular;
- Windows 3.11 checkboxes may be square, but its radios remain circular;
- fallback theme images must not paint over the intended control color;
- symbolic glyphs must remain available even when the active icon theme changes.

Switches should clearly communicate on/off state with a moving slider and a visible checked trough.

## Windows and titlebars

Compiz is the only window manager. `gtk-window-decorator` draws the window frames using the selected Metacity/Marco theme.

Window design should provide:

- reliable resize borders and click targets;
- visible focused and unfocused states;
- readable title text;
- title buttons large enough to use comfortably;
- frame colors coordinated with the GTK theme;
- no silent fallback to another window manager.

The version-3 Metacity themes consume semantic `wm_*` colors from GTK. Geometry or drawing changes belong in the Metacity XML, while ordinary palette changes should begin in the GTK theme.

## Panel and dock

Every theme uses the same panel applet composition:

```text
[Brisk Menu] [Window List] ........ [Volume] [Notification Area] [Clock] [Show Desktop]
```

The panel is 30 px high by default.

- Android and macOS place it at the top and use Cairo Dock at the bottom.
- Other themes keep it at the bottom without Cairo Dock.
- Theme switching moves and resizes the existing panel rather than replacing it.
- The panel's outer toplevel background and its GTK child widgets must be considered separately.

Theme-specific panel treatments are allowed where they are essential to the source identity, such as the Windows XP Luna taskbar or Windows 11's quiet taskbar buttons.

## Icons

Each selectable theme owns a `Spaced-Icons-*` overlay.

Design rules:

- folder and home colors are immutable parts of the selected icon theme;
- normal application coverage is inherited from Papirus Dark;
- menu/trash contrast is provided by shared dark- and light-surface overlays;
- Linux Dark and Linux Light may carry additional coherent device and volume artwork;
- theme switching never rewrites Papirus files;
- symbolic control glyphs have hicolor fallbacks and use the active CSS color.

Icons may use color even when ordinary Spaced Linux chrome is monochrome. Icons communicate category and object identity and should remain recognizable.

## Wallpapers

Wallpapers are coordinated suggestions, not permanent locks.

- MATE's settings daemon is the sole wallpaper painter.
- Selecting a registered theme may apply its suggested wallpaper once.
- A user's later wallpaper choice is preserved across login by the theme monitor.
- Every wallpaper has a sensible solid fallback color.
- Wallpaper changes must not require Compiz restarts, Caja restarts, or root-pixmap helper daemons.

## Typography

Typography should favor readability over novelty.

- Keep application text at a conventional desktop size.
- Avoid low-contrast gray-on-gray combinations.
- Do not rely on color alone to indicate control state.
- Keep labels readable on theme-specific gradients and panel surfaces.
- Preserve clear disabled and unfocused states without making them disappear.

Font-family and size defaults belong in desktop settings, not hard-coded throughout theme CSS.

## Terminal

The default terminal deliberately uses explicit colors rather than following every GTK surface automatically.

- Dark registered themes use black with medium-gray text.
- Light registered themes use white with black text.
- The default ANSI palette remains available for command-line meaning.
- Theme switching changes background and foreground, while the schema supplies the default bold color and 16-color palette.

The current terminal background type is solid; documentation should not promise transparency.

## Compiz presentation

Compiz is part of the visual identity, not an optional afterthought.

The default profile provides:

- four horizontal viewports;
- cube and rotate;
- scale and switcher;
- enhanced zoom;
- transitions and animation;
- a dark cube background and blue-black skydome gradient.

Effects must not compromise boot reliability, input, window management, accessibility, or testability. VM configurations use one stable VGA device to avoid dual-GPU black-screen failures.

## Cross-toolkit boundaries

Spaced asks LibreOffice and Qt Widgets applications to integrate with GTK3.

Current limitations are intentional and must be documented:

- Qt Quick Controls are globally configured as Universal Dark with a fixed gray accent;
- GTK4 and libadwaita applications do not consume the Spaced GTK3 engine;
- Flatpak theme propagation mainly benefits GTK3 applications that permit host themes;
- third-party applications may supply their own colors and CSS.

Visual consistency is a goal, not a reason to misrepresent unsupported toolkits.

## Static previews

Appearance Preferences cards are committed `preview.png` files.

They are documentation and selection aids, not live render tests. Every visual change should consider whether the corresponding preview needs to be regenerated or replaced.

A preview must never be treated as proof that the installed CSS is current.

## Accessibility and quality checks

Every theme change should be reviewed for:

- text contrast;
- visible focus indication;
- selected and active state clarity;
- checked mark and radio-dot contrast;
- disabled-state visibility;
- titlebar focus distinction;
- panel and menu readability;
- icon visibility on light and dark surfaces;
- GTK2 and GTK3 consistency where both are supported;
- live rendering and static preview accuracy.

Automated validation catches structural problems. It does not replace visual inspection.

## Non-goals

Spaced Linux does not aim to:

- duplicate every historical operating-system widget exactly;
- maintain eleven copies of the same GTK engine;
- recolor upstream Papirus files at runtime;
- restart the panel for cosmetic changes;
- force a wallpaper after the user replaces it;
- claim that GTK3 CSS themes GTK4/libadwaita;
- sacrifice legibility for nostalgia.

## Contributor rule of thumb

Start with the narrowest owner of the visual behavior:

1. semantic palette in the active theme;
2. theme-specific tail rule;
3. shared check/radio or switch rule;
4. general shared GTK engine;
5. Metacity XML for frame drawing;
6. icon, wallpaper, panel, terminal, Compiz, or toolkit-specific source.

Test the installed file in a newly launched live application, then update the static preview if needed.
