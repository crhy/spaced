#!/usr/bin/python3
"""Spaced GPU Manager design prototype — FAKE DATA ONLY (issue #426 design review).

Renders each designed page (first-run, overview, roles, move-monitor, drivers) to a PNG
under Xvfb so rhY can approve the look and flow before any code ships.

    xvfb-run -a env GTK_THEME=Spaced-Linux-Dark XDG_DATA_DIRS=.../usr/share:$XDG_DATA_DIRS \
        python3 gpu_manager_prototype.py --capture overview --out screens/overview-spaced-dark.png

Tokens and CSS are Spaced Monitor's (theme.py) so the prototype proves the family look
of STYLE.md; nothing here ships.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk, Pango

# ---------------------------------------------------------------- palette tokens
# Copied from spaced_monitor/theme.py (DARK/LIGHT) so this prototype cannot drift from
# the family look it is meant to prove.


def _hex(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


@dataclass(frozen=True)
class Palette:
    window: tuple
    card: tuple
    border: tuple
    text: tuple
    muted: tuple
    selected_bg: tuple
    gpu_start: tuple
    gpu_end: tuple
    gpu_memory_start: tuple
    gpu_memory_end: tuple
    quiet: tuple
    attention: tuple
    danger: tuple
    gauge_track: tuple


DARK = Palette(
    window=_hex("#0b1220"), card=_hex("#111a2e"), border=_hex("#1e2a44"),
    text=_hex("#e6ecf5"), muted=_hex("#8a96ab"), selected_bg=_hex("#0ea5e9"),
    gpu_start=_hex("#0ea5e9"), gpu_end=_hex("#38bdf8"),
    gpu_memory_start=_hex("#8b5cf6"), gpu_memory_end=_hex("#c084fc"),
    quiet=_hex("#22c55e"), attention=_hex("#f59e0b"), danger=_hex("#ef4444"),
    gauge_track=_hex("#1e2a44"),
)

LIGHT = Palette(
    window=_hex("#eef2f8"), card=_hex("#ffffff"), border=_hex("#dfe5ef"),
    text=_hex("#1f2937"), muted=_hex("#6b7280"), selected_bg=_hex("#0ea5e9"),
    gpu_start=_hex("#0ea5e9"), gpu_end=_hex("#38bdf8"),
    gpu_memory_start=_hex("#8b5cf6"), gpu_memory_end=_hex("#c084fc"),
    quiet=_hex("#22c55e"), attention=_hex("#f59e0b"), danger=_hex("#ef4444"),
    gauge_track=_hex("#e5e7eb"),
)


def _css_colour(colour):
    return "#{:02x}{:02x}{:02x}".format(*(int(c * 255) for c in colour))


def css(pal):
    w, c, b = (_css_colour(pal.window), _css_colour(pal.card), _css_colour(pal.border))
    t, m, s = _css_colour(pal.text), _css_colour(pal.muted), _css_colour(pal.selected_bg)
    purple = _css_colour(pal.gpu_memory_start)
    return f"""\
window, .background {{ background-color: {w}; color: {t}; }}
.headerbar {{ background-color: {c}; border-bottom: 1px solid {b}; padding: 6px 10px; }}
button {{ background-image: none; background-color: {c}; color: {t};
  border: 1px solid {b}; border-radius: 6px; padding: 4px 10px; min-height: 0; }}
button:hover, button:active, button:focus {{ background-color: {c}; }}
button.chip {{ border-radius: 999px; padding: 2px 10px; font-size: 11px; }}
button.suggested {{ background-color: {s}; color: #ffffff; border: none; }}
button.caution {{ background-color: {c}; color: {t}; }}
.card {{ background-color: {c}; border: 1px solid {b}; border-radius: 12px;
  padding: 10px; color: {t}; }}
.card-title {{ font-weight: bold; font-size: 13px; color: {t}; }}
.big-value {{ font-weight: bold; font-size: 13px; color: {t}; }}
.muted {{ font-size: 11px; color: {m}; }}
.value {{ font-size: 13px; color: {t}; }}
.badge {{ font-size: 11px; color: {m}; }}
.chip-desktop {{ background-color: rgba(14,165,233,0.20); color: {t}; border: 1px solid {s};
  border-radius: 999px; padding: 2px 10px; font-size: 11px; }}
.chip-compute {{ background-color: rgba(139,92,246,0.20); color: {t}; border: 1px solid {purple};
  border-radius: 999px; padding: 2px 10px; font-size: 11px; }}
.chip-off {{ background-color: {c}; color: {m}; border: 1px solid {b};
  border-radius: 999px; padding: 2px 10px; font-size: 11px; }}
.vram {{ color: {purple}; }}
.warn {{ color: {t}; }}
.footer {{ background-color: {c}; border: 1px solid {b}; border-radius: 12px;
  padding: 6px 10px; color: {t}; }}
.hint {{ font-size: 11px; color: {m}; }}
page-title {{ font-weight: bold; font-size: 15px; }}
list, list row {{ background-color: {c}; color: {t}; border: none; }}
entry {{ background-color: {c}; color: {t}; border: 1px solid {b}; border-radius: 6px;
  padding: 4px 8px; }}
"""


# ---------------------------------------------------------------- fake bigboy data
# bigboy 2026-11-20: 1080p monitor on the 4070's HDMI; Xorg+Compiz hold ~310 MiB.

GPUS = [
    dict(name="GeForce RTX 4070 Ti SUPER", vendor="NVIDIA", vram="16 GB",
         vram_used="0.3", vram_fraction=0.02, driver="NVIDIA 570.172.08 (installed by Spaced)",
         link="PCIe 4.0 · 16 lanes", link_note="",
         monitor="Your screen: HDMI 2 · 1920 × 1080",
         sockets="Two sockets: DisplayPort, HDMI", role="Desktop",
         badge="NVIDIA · 16 GB · drives your screen",
         ports_free=""),
    dict(name="GeForce RTX 3050", vendor="NVIDIA", vram="8 GB",
         vram_used="0", vram_fraction=0.0, driver="NVIDIA 570.172.08 (installed by Spaced)",
         link="PCIe 4.0 · 16 lanes", link_note="· running at 4 lanes because of the slot it's in",
         monitor="Nothing plugged in",
         sockets="Two sockets: DisplayPort, HDMI (both free)", role="AI & compute",
         badge="NVIDIA · 8 GB · AI & compute", ports_free=""),
    dict(name="Radeon 610M", vendor="AMD", vram="shared", vram_used="", vram_fraction=None,
         vram_note="Shared with your PC · about 2 GB available to graphics",
         driver="AMD's own driver (already in Spaced)",
         link="PCIe (built into your CPU)", link_note="",
         monitor="Ports free: DisplayPort, HDMI",
         sockets="Two sockets near the USB ports: DisplayPort 1, HDMI 1 (nothing plugged in)",
         role="Off", badge="AMD · built into your CPU",
         ports_free=""),
]


# ---------------------------------------------------------------- widget helpers
def _wrap(lbl):
    lbl.set_line_wrap(True)
    lbl.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
    lbl.set_max_width_chars(60)
    return lbl


def label(text, css_class="value"):
    lbl = Gtk.Label(label=text)
    lbl.get_style_context().add_class(css_class)
    lbl.set_xalign(0.0)
    return _wrap(lbl)


def row(*widgets, spacing=8):
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=spacing)
    for w in widgets:
        box.pack_start(w, False, False, 0)
    return box


def vbox(spacing=6, margin=0):
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing)
    if margin:
        box.set_margin_top(margin)
        box.set_margin_bottom(margin)
        box.set_margin_start(margin)
        box.set_margin_end(margin)
    return box


def card_box(spacing=6):
    box = vbox(spacing)
    box.set_margin_top(10)
    box.set_margin_bottom(10)
    box.set_margin_start(12)
    box.set_margin_end(12)
    box.get_style_context().add_class("card")
    return box


def vram_bar(gpu):
    bar = Gtk.ProgressBar()
    if gpu["vram_fraction"] is None:
        bar.set_text(gpu["vram_note"])
        bar.set_show_text(True)
        return bar
    bar.set_fraction(gpu["vram_fraction"])
    bar.set_text(f"VRAM {gpu['vram_used']} of {gpu['vram']} used")
    bar.set_show_text(True)
    bar.get_style_context().add_class("vram")
    return bar


def chip(role):
    ev = Gtk.EventBox()
    lbl = Gtk.Label(label=role)
    ev.add(lbl)
    ev.get_style_context().add_class(
        {"Desktop": "chip-desktop", "AI & compute": "chip-compute"}.get(role, "chip-off"))
    return ev


# ---------------------------------------------------------------- the pages
class Prototype(Gtk.Window):
    def __init__(self, pal, page):
        super().__init__(title="Spaced GPU Manager")
        self.pal = pal
        self.set_default_size(900, 680)
        self.set_size_request(720, 540)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.connect("destroy", Gtk.main_quit)

        header = Gtk.HeaderBar()
        header.set_show_close_button(True)
        header.set_title("Spaced GPU Manager")
        header.set_subtitle("Three graphics cards · your screen is on the GeForce RTX 4070 Ti SUPER")
        refresh = Gtk.Button(label="⟳ refresh")
        header.pack_end(refresh)
        self.set_titlebar(header)

        root = vbox(0)
        self.add(root)

        if page == "first-run":
            root.pack_start(self.first_run(), True, True, 0)
        else:
            bar = row(label(""), spacing=6)
            current = {"overview": "Overview", "roles": "Roles",
                       "move-monitor": "Move monitor", "drivers": "Drivers"}[page]
            for name in ("Overview", "Roles", "Move monitor", "Drivers"):
                btn = Gtk.Button(label=name)
                if name == current:
                    btn.get_style_context().add_class("suggested")
                bar.pack_start(btn, False, False, 0)
            root.pack_start(bar, False, False, 10)
            body = {"overview": self.overview, "roles": self.roles,
                    "move-monitor": self.move_monitor, "drivers": self.drivers}[page]()
            scroller = Gtk.ScrolledWindow()
            scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            scroller.add(body)
            root.pack_start(scroller, True, True, 0)
            one = label("Your desktop is using 310 MB of the RTX 4070 Ti SUPER. Moving the "
                        "desktop to the CPU's graphics frees it for games and AI — Roles explains the trade.")
            one.get_style_context().add_class("footer")
            root.pack_start(one, False, False, 10)

    def gpu_card(self, gpu):
        card = card_box(6)
        card.pack_start(label(gpu["name"], "card-title"), False, False, 0)
        card.pack_start(row(label(gpu["badge"], "muted"), chip(gpu["role"])), False, False, 0)
        card.pack_start(vram_bar(gpu), False, False, 0)
        link = label(gpu["link"], "value")
        card.pack_start(row(link, label(gpu["link_note"], "muted")), False, False, 0)
        card.pack_start(label(gpu["monitor"], "value"), False, False, 0)
        card.pack_start(label(gpu["sockets"], "muted"), False, False, 0)
        buttons = row(Gtk.Button(label="Set up…"),
                      Gtk.Button(label="Move my screen here…"))
        card.pack_start(buttons, False, False, 0)
        return card

    def overview(self):
        box = vbox(10)
        for gpu in GPUS:
            box.pack_start(self.gpu_card(gpu), False, False, 0)
        box.set_margin_start(10)
        box.set_margin_end(10)
        return box

    def roles(self):
        box = vbox(10)
        box.set_margin_start(10)
        box.set_margin_end(10)
        box.pack_start(label("What each card is for", "card-title"), False, False, 0)
        for gpu in GPUS:
            card = card_box(6)
            card.pack_start(label(gpu["name"], "card-title"), False, False, 0)
            card.pack_start(label(gpu["badge"], "muted"), False, False, 0)
            card.pack_start(chip(gpu["role"]), False, False, 0)
            card.pack_start(label(
                {"Desktop": "Draws your screen. Everything you see runs on this card.",
                 "AI & compute": "Saves this card for your AI work. Spaced gives your AI "
                                 "programs this card by its real name, so they can't end up "
                                 "on the wrong one.",
                 "Off": "Leave it alone. Nothing starts here unless you say so. The card can "
                        "still be used for your screen."}[gpu["role"]], "value"), False, False, 0)
            card.pack_start(row(Gtk.Button(label="Change role…"),
                                Gtk.Button(label="Undo")), False, False, 0)
            box.pack_start(card, False, False, 0)
        hint = card_box(6)
        hint.pack_start(label("Your CPU has its own graphics (Radeon 610M). If you plug your "
                              "screen into the motherboard's socket, your desktop moves onto it "
                              "and the whole 16 GB of the RTX 4070 Ti SUPER is free for AI and "
                              "games.", "value"), False, False, 0)
        hint.pack_start(row(Gtk.Button(label="Move my screen to the CPU's graphics", ),
                            label("Spaced 11.26.4 cannot switch a graphics card off to save power.", "hint")),
                        False, False, 0)
        box.pack_start(hint, False, False, 0)
        return box

    def move_monitor(self):
        box = vbox(10)
        box.set_margin_start(10)
        box.set_margin_end(10)
        box.pack_start(label("Move your screen onto the CPU's graphics", "card-title"), False, False, 0)
        why = card_box(6)
        why.pack_start(label("Why", "card-title"), False, False, 0)
        why.pack_start(label("Your desktop uses 310 MB of the RTX 4070 Ti SUPER. Moving the "
                             "desktop onto your CPU's own graphics frees all 16 GB for AI and "
                             "games.", "value"), False, False, 0)
        why.pack_start(label("Cost, honestly: games on the 4070 run a few percent slower and a "
                             "little laggier, some NVIDIA features (G-Sync) don't work across "
                             "cards, and your motherboard's socket may support fewer screens "
                             "than the 4070's. Spaced measures nothing until it is done and "
                             "will show you what changed.", "muted"), False, False, 0)
        box.pack_start(why, False, False, 0)

        step1 = card_box(6)
        step1.pack_start(label("1 · Find the right socket", "card-title"), False, False, 0)
        step1.pack_start(label("Your CPU's graphics has these sockets, on the back of the PC "
                               "near the USB ports:", "value"), False, False, 0)
        step1.pack_start(label("• DisplayPort 1 (nothing plugged in)", "value"), False, False, 0)
        step1.pack_start(label("• HDMI 1 (nothing plugged in)", "value"), False, False, 0)
        step1.pack_start(label("Your screen is in: HDMI 2 — on the GeForce RTX 4070 Ti SUPER.",
                               "value"), False, False, 0)
        step1.pack_start(label("Sockets are grouped by card on the back of every PC; the "
                               "motherboard's group is next to the USB and audio jacks.", "muted"),
                         False, False, 0)
        box.pack_start(step1, False, False, 0)

        step2 = card_box(6)
        step2.pack_start(label("2 · Move the cable", "card-title"), False, False, 0)
        step2.pack_start(label("Turn the PC off first, then move the cable from the wide HDMI "
                               "socket halfway down the PC (next to the 4070's other sockets) to "
                               "the HDMI socket up near the USB ports.", "value"), False, False, 0)
        box.pack_start(step2, False, False, 0)

        step3 = card_box(6)
        step3.pack_start(label("3 · Tell Spaced", "card-title"), False, False, 0)
        step3.pack_start(row(Gtk.Button(label="⟳ I've moved the cable"),
                            Gtk.Button(label="Use it for the desktop", )), False, False, 0)
        step3.pack_start(label("Then: your screen goes blank for a few seconds while Spaced "
                               "restarts the desktop. Log in within 3 minutes and press "
                               "“Keep this”. If you do nothing, Spaced puts everything back "
                               "on its own.", "muted"), False, False, 0)
        box.pack_start(step3, False, False, 0)
        return box

    def drivers(self):
        box = vbox(10)
        box.set_margin_start(10)
        box.set_margin_end(10)
        status = card_box(6)
        status.pack_start(label("NVIDIA driver: NVIDIA 570.172.08 · working", "card-title"),
                          False, False, 0)
        status.pack_start(label("Installed by Spaced · verified after the last startup", "muted"),
                          False, False, 0)
        box.pack_start(status, False, False, 0)
        actions = card_box(6)
        actions.pack_start(label("Graphics setup", "card-title"), False, False, 0)
        actions.pack_start(row(Gtk.Button(label="Check graphics"),
                               Gtk.Button(label="Replace working NVIDIA driver"),
                               Gtk.Button(label="Install / repair AMD drivers"),
                               Gtk.Button(label="Restore graphics")), False, False, 0)
        actions.pack_start(label("Before a reboot, Spaced checks: the exact kernel headers, "
                                 "Secure Boot, that the packages exist, that the modules were "
                                 "built, that nothing blocks them, that the boot image contains "
                                 "them, the desktop libraries, the start-up options, and the "
                                 "window-session launcher. After a reboot it checks the card "
                                 "driver again, the NVIDIA tools, 3D, the window session, the "
                                 "panel and the file manager.", "muted"), False, False, 0)
        box.pack_start(actions, False, False, 0)
        log = card_box(6)
        log.pack_start(label("Log", "card-title"), False, False, 0)
        log.pack_start(label("/var/log/spaced-nvidia-installer.log · [ Copy log ]", "value"),
                       False, False, 0)
        box.pack_start(log, False, False, 0)
        links = card_box(6)
        links.pack_start(row(Gtk.LinkButton.new_with_label("https://spacedlinux.com/help.html", "Online Help"),
                             Gtk.LinkButton.new_with_label("https://discord.gg/BMW9Y6NB3y", "Discord"),
                             Gtk.LinkButton.new_with_label("https://t.me/+pjmFzHo-i9A2ZWY5", "Telegram")),
                         False, False, 0)
        box.pack_start(links, False, False, 0)
        return box

    def first_run(self):
        box = vbox(12)
        box.set_margin_start(24)
        box.set_margin_end(24)
        box.set_margin_top(24)
        card = card_box(12)
        card.pack_start(label("Spaced GPU Manager", "card-title"), False, False, 0)
        card.pack_start(label("See your graphics cards, choose what each one does, and move "
                              "your screen between them.", "big-value"), False, False, 0)
        for line in ("Nothing happens until you press a button. Spaced never changes your "
                     "graphics setup on its own.",
                     "Changing which card draws your screen switches your screen off for a few "
                     "seconds and restarts your desktop. Spaced puts everything back if you "
                     "don't confirm it.",
                     "Save your work before you change anything."):
            card.pack_start(label("• " + line, "value"), False, False, 0)
        card.pack_start(row(Gtk.Button(label="Look around"),
                            Gtk.Button(label="Choose my setup")), False, False, 8)
        box.pack_start(card, False, False, 0)
        return box


# ---------------------------------------------------------------- capture
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--capture", choices=["first-run", "overview", "roles", "move-monitor", "drivers"])
    ap.add_argument("--palette", choices=["dark", "light", "system"], default="dark")
    ap.add_argument("--out")
    ap.add_argument("--seconds", type=float, default=1.2)
    args = ap.parse_args()

    pal = {"dark": DARK, "light": LIGHT}[args.palette if args.palette != "system" else "dark"]
    provider = Gtk.CssProvider()
    provider.load_from_data(css(pal).encode())
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)

    if not args.capture:
        win = Prototype(pal, "overview")     # browse by hand: plain overview
        win.show_all()
        Gtk.main()
        return 0

    win = Prototype(pal, args.capture)
    win.show_all()
    GLib.timeout_add_seconds(1, Gtk.main_quit)
    Gtk.main()

    gdk_window = win.get_window()
    if gdk_window is None:
        print("FAIL: no gdk window", file=sys.stderr)
        return 1
    w, h = win.get_size()
    if w < 1 or h < 1:
        print("FAIL: window not allocated", file=sys.stderr)
        return 1
    pixbuf = Gdk.pixbuf_get_from_window(gdk_window, 0, 0, w, h)
    if pixbuf is None:
        print("FAIL: no pixbuf", file=sys.stderr)
        return 1
    ok, data = pixbuf.save_to_bufferv("png", [])
    if not ok:
        print("FAIL: save failed", file=sys.stderr)
        return 1
    open(args.out, "wb").write(data)
    print(f"wrote {args.out} ({w}x{h})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
