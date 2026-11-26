# STYLE.md — the family look the GPU Manager must share

Spaced apps look like one product. The GPU Manager reuses the parts Spaced Monitor,
Spaced Update, Bazaar and Spaced RGB already ship, so the app is not allowed to invent
its own colours, card shapes, icon set or window chrome. Everything below already exists
in a Spaced repository; the new app copies or imports it, it does not redesign it.

Standing rule this implements (docs/notes/spaced-apps-follow-theme.md, rhY 2026-10-31):
every Spaced app takes its colours from the active desktop theme, live. A user-facing
"Never" stays absolute, and no new chrome is invented for the GPU Manager.

## 1. Window chrome (Spaced Update / Bazaar)

| Part | Where it comes from | GPU Manager use |
|---|---|---|
| `Gtk.HeaderBar` with `set_show_close_button(True)`, title + subtitle | `overlays/usr/lib/spaced-linux/spaced-update.py` (`App.__init__`) | title "Spaced GPU Manager", subtitle names the machine's GPUs in plain words ("3 graphics cards · desktop on Radeon 610M") |
| Header buttons from icon names (`view-refresh-symbolic`, `help-about-symbolic`) with tooltips | same file | Refresh, Drivers, About |
| `Gtk.Stack` + centred `Gtk.StackSwitcher` as the page bar | same file | Overview · Roles · Move monitor · Drivers |
| Bottom centred community links (Online Help / Discord / Telegram) | same file | same three links, same URLs |
| 900 × 680 default, 720 × 540 minimum | same file | same numbers, so the app sits the same size on the desktop |
| Dialogs are `Gtk.MessageDialog` with `transient_for` the window, secondary text for detail | `spaced-nvidia-installer.py`, candidate `spaced-gpu-manager.py` | every confirm/warning/error |

Bazaar (`crhy/spacedbazaar`, `src/style.css`) is the other reference for the same
language: small CSS classes attached to stock widgets (`.bz-monospace`,
`.bz-small-button`) rather than custom drawing, and `prefers-color-scheme` for dark.

## 2. Cards, gauges and typography (Spaced Monitor)

The Overview page is built from Spaced Monitor's card system, copied from
`spaced_monitor/cards.py` (GPL-3.0-or-later) into this app:

| Piece | Source | Rule for the GPU Manager |
|---|---|---|
| `.card` box: 1 px border, 12 px radius, card background | `cards.py` `_CardBase`, `theme.py` `css()` `.card` | one card per GPU, exactly like the CPU/GPU/MEMORY cards |
| `_title()` / `_big()` / `_value` / `_muted()` label helpers | `cards.py` | card title = GPU name (13 px bold), headline number = big value, detail lines = value/muted |
| `Gauge` (arc gauge, `kind` gradient) | `spaced_monitor/widgets.py` `Gauge` | VRAM used as a gauge per card, same geometry as Monitor's GPU MEMORY card |
| `StackedBar` | `widgets.py` | one bar showing what the card is doing: desktop / games / AI share of that GPU's VRAM |
| `Meter`, `Sparkline`, `LineGraph` | `widgets.py` | not used on Overview; available if a live "in use" strip is wanted later |
| `_wrap()` label wrapping, `set_max_width_chars`, the `_Sizing` re-measure mixin | `cards.py` | keeps cards readable at 880 px wide without cutting text off |
| Footer row of small items with separators (`.footer`, `.footer-item`, `.footer-sep`) | `theme.py` `css()` | one short line only — never a wall of footer text (rhY's review finding 3) |

Hierarchy, same as Monitor: page → cards → one headline value per card → muted detail
lines. No nested panels, no notebook tabs inside a card, no raw sysfs dumps on the face
of a card.

## 3. Colour tokens (Spaced Monitor `theme.py`)

The app imports Monitor's `Palette` dataclass and its two constants (`DARK`, `LIGHT`)
and uses `palette_from_gtk(style_context)` so colours come from the live desktop theme:

- `window`, `card`, `border`, `text`, `muted`, `selected_bg`, `gauge_track` — chrome;
- `gpu_start` / `gpu_end` — the GPU identity gradient (blue, Monitor's GPU colour);
- `gpu_memory_start` / `gpu_memory_end` — VRAM (violet, Monitor's GPU MEMORY colour);
- `cpu_start` / `cpu_end` — "quiet / free / safe" green;
- `memory_start` / `cpu_temp` — attention amber;
- `threshold`, `end_button` — red, reserved for the two dangerous things: the
  "this will end your session" trial and the "restore" action. Red is used nowhere else;
- `resolve_theme()` / `apply_css()` — the theme switch happens live, and every widget
  is re-paetted (`set_palette`) on switch, exactly as Monitor does.

Because every Spaced metatheme (Spaced Linux Dark/Light, the Windows/macOS/Mint/Ubuntu
interpretations) exposes `theme_bg_color`, `theme_base_color`, `theme_fg_color` and
`theme_selected_bg_color`, the app follows rhY's desktop without shipping its own
palette. The prototype in `prototype/` renders one dark and one light screen with these
same tokens to prove it.

Vendor identity never comes from vendor colours. NVIDIA green, AMD red and Intel blue
are not used; vendor is a word in the card and a shape in the icon. This keeps the app
monochrome-by-default like `docs/DESIGN.md` asks, and readable in every theme.

## 4. Icons

- Window/dialog icon: stock `video-display` (already the shipped .desktop `Icon=`), so
  the app is findable in the Brisk menu with no new artwork.
- Card badge: a symbolic 24 px "graphics card" glyph (a board with a fan) plus a
  second glyph for the integrated GPU (a CPU die with the same fan corner) so the three
  cards are visually different without colour. Spaced RGB's symbolic menu icon work
  (f109) shows the pattern: one symbolic SVG in
  `usr/share/icons/Spaced-Icons-*/scalable/devices/`, tinted by the theme.
- Port glyphs in the Move-monitor page: DP, HDMI, USB-C as tiny text badges, not
  pictures — text is honest about the connector name and stays legible in all themes.
- Role icons (Desktop / AI & compute / Games / Off) are symbolic stock names where
  they exist (`user-desktop`, `cpu`, `applications-games`, `process-stop`), so the
  theme colours them for free.

## 5. Type and number formatting

Monitor's `format.py` is reused as-is: `bytes_gb`, `pair_gb`, `temp`, `watts`,
`percent`, `EMDASH` for unknown values. The GPU Manager adds exactly two helpers:
PCIe width/speed ("PCIe 4.0 ×16", with the live value only in the detail line) and
VRAM "12.6 GiB of 12 GiB" style pairs. Unknown values are em dashes, never 0, never
"unavailable" prose on the card face (that text belongs in a tooltip).

## 6. Copy style (applies to DESIGN.md strings)

- Plain words, no engineer jargon. Never "scanout", "PCIe 2.5 GT/s", "BusID",
  "X provider", "render offload", "modprobe" on a user-facing surface.
- The card answers four questions in this order: what is this card, is my screen on it,
  how much memory does it have and how full is it, what is it for.
- Every action states what changes, what it costs, and how to undo it, in that order.
- Honest costs are stated as ranges, not promises ("a few percent slower in games"), and
  things this version does not do are stated once, in the page, not repeated in a footer.
