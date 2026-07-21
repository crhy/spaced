# Keep terminal-launched desktop processes consistent with the graphical MATE
# session. The paths are included even before the first Flatpak is installed.
XDG_DATA_DIRS=${XDG_DATA_DIRS:-/usr/local/share:/usr/share}

case ":$XDG_DATA_DIRS:" in
    *":$HOME/.local/share/flatpak/exports/share:"*) ;;
    *) XDG_DATA_DIRS="$HOME/.local/share/flatpak/exports/share:$XDG_DATA_DIRS" ;;
esac

case ":$XDG_DATA_DIRS:" in
    *":/var/lib/flatpak/exports/share:"*) ;;
    *) XDG_DATA_DIRS="/var/lib/flatpak/exports/share:$XDG_DATA_DIRS" ;;
esac

export XDG_DATA_DIRS
