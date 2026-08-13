# Spaced Linux theming reference

This filename is retained so old links continue to work. The former contents described a retired theme watcher, Papirus symlink rewriting, and other implementation details that are no longer used.

Current documentation:

- [MATE theme architecture](docs/MATE-theming.md) — selectable themes, the shared GTK engine, runtime switching, installation, testing, and contributor workflow.
- [Theme and interface color reference](docs/THEME-COLORS.md) — GTK palettes, controls, panels, window decorations, icons, wallpapers, terminal colors, Flatpak propagation, and cross-toolkit limitations.
- [MATE panel layout](docs/matepanel.md) — panel objects, orientation, size, background handling, and Cairo Dock behavior.
- [Visual design](docs/DESIGN.md) — current design principles for the Spaced identity and the OS-inspired themes.

The authoritative implementation remains the source under `overlays/`, especially:

```text
overlays/usr/share/themes/
overlays/usr/share/icons/
overlays/usr/share/spaced-themes/themes.json
overlays/usr/local/bin/spaced-theme-monitor
overlays/usr/local/bin/spaced-switch-theme
```
