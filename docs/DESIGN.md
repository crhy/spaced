# Spaced Linux 7.26 Design

## Base System
- **Distro:** Devuan Ceres 7 (Freia) — rolling release, no systemd
- **Init:** sysvinit
- **Build:** QEMU/KVM VM → manual live ISO build later

## Desktop
- **Environment:** MATE 1.26
- **Window manager:** Compiz by default; Marco is the automatic fallback
- **Compiz effects:** Desktop cube/rotate, wobbly windows, fade, grid, animation, scale, and switcher
- **Display Manager:** LightDM (autologin)
- **Default Session:** MATE with Compiz as window manager

## Panel Layout (Windows XP Style)

Single bottom panel, 28px:
```
[Brisk Menu] [Window List] .............................. [Notification Area] [Clock]
```
- **Brisk Menu** — far left, with Simple Icon
- **Window List** — immediately right of Brisk Menu (app switcher)
- **Spacer** — expandable, pushes right items to the right
- **Notification Area** — just left of the clock
- **Clock** — far right, 12-hour format, no date

## Theming

### Color Palette
- **Primaries:** Black, grays — zero color except icons
- **Accent None.** No blues, greens, reds, etc. on UI elements
- **Dialogs:** Monochrome
- **Window borders:** Monochrome
- **All UI chrome:** Shades of black/gray only

### Theme
- **Base:** BlackMATE (from Devuan repos)
- **Modifications:** Darker tones, all color stripped, only grayscale remains
- **GTK:** Custom Spaced-Dark based on BlackMATE
- **Icons:** Per-theme folder overlays inheriting Papirus Dark
- **Font:** Noto Sans 10, monospace: Fira Code 10 or similar

### Terminal
- Background: Black
- Text: Light gray
- Transparency: Semi-transparent (on composited desktop)
- Color scheme: Gray-on-black, no ANSI color clashes

### Backgrounds
- **GRUB:** `SimpleBackc.png` (or SimpleBackb.png) — subtle, low contrast
- **LightDM:** `SimpleBackc.png` — same subtle background
- **Desktop:** `SpacedBack.png` — fancy/full artwork

### Icons
- **Brisk Menu:** `spaced.png` — simple S icon (16KB)
- **LightDM greeter:** `SpacedIconb.png` — fancy full icon (1MB)
- **Desktop icon theme:** A matching `Spaced-Icons-*` overlay over Papirus Dark

## Applications

### System (native debs)
- MATE desktop core, Compiz, Marco fallback, LightDM, NetworkManager
- Flatpak + Flathub
- MATE terminal, Caja file manager, Pluma text editor
- Synaptic, Gdebi
- Btop, Fastfetch

### User Applications (Flatpak)
All user apps installed via Flatpak/Flathub:
- Browser, media player, office, chat, etc.

### Removed Bloat
- GIMP (use Flatpak if needed)
- LibreOffice (use Flatpak if needed)
- Firefox (use Flatpak if needed)
- Any task-* meta-packages not needed

## Visual Identity
- Name: Spaced Linux
- Codename: 726
- Monochrome aesthetic with Spaced iconography

## Future
- Calamares installer for live ISO
- Custom GRUB theme (monochrome)
- Custom Plymouth boot splash (monochrome)
- Live ISO with squashfs
