# Make cross-toolkit desktop applications follow the Spaced GTK theme.
export SAL_USE_VCLPLUGIN=gtk3
export QT_QPA_PLATFORMTHEME=gtk3
# QGtkStyle can lose indicator artwork when a GTK theme is exported into a
# Flatpak. Fusion keeps Qt Widgets controls (notably Dolphin check boxes)
# native and complete while QGtk3Theme continues to supply the active palette.
export QT_STYLE_OVERRIDE=Fusion
