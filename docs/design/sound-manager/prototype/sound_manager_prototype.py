#!/usr/bin/python3
"""Spaced Sound Manager design prototype — FAKE DATA ONLY (issue #429 design review).

Renders each designed page (output, input, applications, effects, advanced) to a PNG
under Xvfb so rhY can approve the look and flow before any code ships.

    xvfb-run -a env GTK_THEME=Spaced-Dark XDG_DATA_DIRS=.../usr/share:$XDG_DATA_DIRS \
        python3 sound_manager_prototype.py --capture output --out screens/output-spaced-dark.png

Tokens and CSS follow Spaced Monitor's theme.py (STYLE.md §3, reused from the GPU
Manager's STYLE.md) so the prototype proves the family look; nothing here ships.
The prototype never plays sound and never opens a microphone: `play-test-sound` is a
no-op unless --i-was-clicked is given, and there is no real backend at all.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, GLib, Gtk, Pango

# ---------------------------------------------------------------- palette tokens
# Copied from spaced_monitor/theme.py (DARK/LIGHT) exactly as the GPU Manager's
# STYLE.md reuses them, plus the sound tokens DESIGN.md §6 adds.


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
    quiet: tuple            # Monitor's cpu_* green: a quiet, healthy signal
    attention: tuple        # amber: approaching 0 dB
    danger: tuple           # red: clipping / mute / the one restart action
    level_start: tuple
    level_mid: tuple
    level_peak: tuple
    meter_track: tuple


DARK = Palette(
    window=_hex("#0b1220"), card=_hex("#111a2e"), border=_hex("#1e2a44"),
    text=_hex("#e6ecf5"), muted=_hex("#8a96ab"), selected_bg=_hex("#0ea5e9"),
    quiet=_hex("#22c55e"), attention=_hex("#f59e0b"), danger=_hex("#ef4444"),
    level_start=_hex("#22c55e"), level_mid=_hex("#f59e0b"), level_peak=_hex("#ef4444"),
    meter_track=_hex("#1e2a44"),
)

LIGHT = Palette(
    window=_hex("#eef2f8"), card=_hex("#ffffff"), border=_hex("#dfe5ee"),
    text=_hex("#1f2937"), muted=_hex("#6b7280"), selected_bg=_hex("#0ea5e9"),
    quiet=_hex("#22c55e"), attention=_hex("#f59e0b"), danger=_hex("#ef4444"),
    level_start=_hex("#22c55e"), level_mid=_hex("#f59e0b"), level_peak=_hex("#ef4444"),
    meter_track=_hex("#e5e7eb"),
)


def _css_colour(c):
    return "#{:02x}{:02x}{:02x}".format(*(int(x * 255) for x in c))


def css(pal):
    w, c, b = (_css_colour(pal.window), _css_colour(pal.card), _css_colour(pal.border))
    t, m = _css_colour(pal.text), _css_colour(pal.muted)
    track = _css_colour(pal.meter_track)
    selected = _css_colour(pal.selected_bg)
    red = _css_colour(pal.level_peak)
    return f"""\
window, .background {{ background-color: {w}; color: {t}; }}
.headerbar {{ background-color: {c}; border-bottom: 1px solid {b}; padding: 6px 10px; }}
button {{ background-image: none; background-color: {c}; color: {t};
  border: 1px solid {b}; border-radius: 6px; padding: 4px 10px; min-height: 0; }}
button:hover, button:active, button:focus {{ background-color: {c}; }}
button.suggested {{ background-color: {selected}; color: #ffffff; border: none; }}
button.danger {{ background-color: {red}; color: #ffffff; border: none; }}
button.chip {{ border-radius: 999px; padding: 2px 10px; font-size: 11px; }}
.card {{ background-color: {c}; border: 1px solid {b}; border-radius: 12px;
  padding: 10px; color: {t}; }}
.card-title {{ font-weight: bold; font-size: 13px; color: {t}; }}
.big-value {{ font-weight: bold; font-size: 13px; color: {t}; }}
.value {{ font-size: 13px; color: {t}; }}
.muted {{ font-size: 11px; color: {m}; }}
.badge {{ font-size: 11px; color: {m}; }}
.warn {{ color: {red}; font-size: 11px; }}
.hint {{ font-size: 11px; color: {m}; }}
.footer {{ background-color: {c}; border: 1px solid {b}; border-radius: 12px;
  padding: 6px 10px; color: {t}; }}
page-title {{ font-weight: bold; font-size: 15px; }}
list, list row {{ background-color: {c}; color: {t}; border: none; }}
stackswitcher {{ background-color: transparent; border: none; }}
stackswitcher button {{ border-radius: 999px; }}
scale highlight {{ background-color: {selected}; }}
scale trough {{ background-color: {track}; }}
expander {{ color: {m}; }}
frame {{ color: {t}; }}
frame > label {{ color: {m}; }}
"""


# ------------------------------------------------- fake bigboy data (never real)
# bigboy 2026-11-21 as issue #429 describes it: two NVIDIA HDMI outputs on the
# RTX 4070 Ti SUPER, onboard HD-Audio analog, a Blue Microphones USB microphone and
# a Galyimage webcam. Levels are drawn from these fixed numbers: nothing is measured,
# no audio device is opened.
OUTPUTS = [
    dict(name="LG monitor (HDMI on RTX 4070 Ti SUPER)", icon="video-display-symbolic",
         kind="HDMI · stereo · plugged into the RTX 4070 Ti SUPER",
         connectors=["HDMI 1", "DisplayPort (nothing plugged in)"], selected=True,
         volume=60, muted=False, levels=(0.62, 0.58), peak=-4, raw="alsa_output.pci-0000_01_00.1.hdmi-stereo"),
    dict(name="TCL TV (HDMI on RTX 4070 Ti SUPER)", icon="video-display-symbolic",
         kind="HDMI · stereo · nothing plugged in", connectors=["HDMI 2"],
         selected=False, volume=45, muted=False, levels=(0.0, 0.0), peak=None,
         raw="alsa_output.pci-0000_01_00.1.hdmi-stereo-extra1"),
    dict(name="Speakers (onboard audio)", icon="audio-speakers-symbolic",
         kind="3.5 mm jack · green socket", connectors=["Speaker", "Headphones (plugged in)"],
         selected=False, volume=75, muted=False, levels=(0.31, 0.34), peak=-12,
         raw="alsa_output.pci-0000_00_1f.3.analog-stereo"),
    dict(name="Headphones (onboard audio, green jack)", icon="audio-headphones-symbolic",
         kind="3.5 mm jack · plugged in", connectors=["Headphones (plugged in)"],
         selected=False, volume=40, muted=True, levels=(0.0, 0.0), peak=None,
         raw="alsa_output.pci-0000_00_1f.3.analog-stereo"),
]

INPUTS = [
    dict(name="Blue Yeti microphone (USB)", icon="audio-input-microphone-symbolic",
         kind="USB · mono · plugged in", selected=True, volume=80, muted=False,
         levels=(0.44,), peak=-8, raw="alsa_input.usb-BLUE_MICROPHONE_00000000000000.0.mono-input",
         extra=""),
    dict(name="Galyimage webcam microphone", icon="audio-input-microphone-symbolic",
         kind="USB · mono · plugged in", selected=False, volume=55, muted=False,
         levels=(0.05,), peak=-28, raw="alsa_input.usb-Galyimage_HD_Webcam_2009-02.analog-stereo",
         extra="camera-web-symbolic"),
]

APPS = [
    dict(name="Firefox", icon="firefox-esr", route="LG monitor (HDMI on RTX 4070 Ti SUPER)",
         volume=70, muted=False, levels=(0.51, 0.47), group="Playing"),
    dict(name="VLC media player", icon="vlc", route="LG monitor (HDMI on RTX 4070 Ti SUPER)",
         volume=100, muted=False, levels=(0.83, 0.79), group="Playing"),
    dict(name="Spaced Sound Manager (test sound)", icon="multimedia-volume-control",
         route="LG monitor (HDMI on RTX 4070 Ti SUPER)", volume=50, muted=False,
         levels=(0.66, 0.62), group="Playing"),
    dict(name="Voice2Text", icon="audio-input-microphone-symbolic",
         route="Blue Yeti microphone (USB)", volume=85, muted=False,
         levels=(0.44,), group="Recording"),
]

PAGES = ["output", "input", "applications", "effects", "advanced"]


# ---------------------------------------------------------------- small helpers
def label(text, style=None, wrap=False):
    lab = Gtk.Label(label=text)
    if style:
        lab.get_style_context().add_class(style)
    if wrap:
        lab.set_line_wrap(True)
        lab.set_xalign(0)
        lab.set_width_chars(40)
        lab.set_max_width_chars(80)
    return lab


def vbox(spacing=6):
    b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing)
    return b


def hbox(spacing=6):
    return Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=spacing)


def card_box(spacing=6):
    box = vbox(spacing)
    box.get_style_context().add_class("card")
    box.set_margin_bottom(2)
    return box


class Meter(Gtk.DrawingArea):
    """Static mock meter: a row of segments painted from fixed fake numbers."""

    def __init__(self, pal, levels, peak_db=None, width=170, height=12):
        super().__init__()
        self.pal, self.levels, self.peak_db = pal, levels, peak_db
        self.set_size_request(width, height)
        self.connect("draw", self._draw)

    def _draw(self, _w, cr):
        alloc = self.get_allocation()
        w, h = alloc.width, alloc.height
        segs = 14
        gap = 2
        sw = (w - gap * (segs - 1)) / segs
        track = self.pal.meter_track
        levels = self.levels or [0.0]
        top = max(levels)
        for i in range(segs):
            frac = (i + 1) / segs
            cr.set_source_rgba(*track, 0.9)
            if frac <= top:
                if frac > 0.86:
                    cr.set_source_rgba(*self.pal.level_peak)
                elif frac > 0.62:
                    cr.set_source_rgba(*self.pal.level_mid)
                else:
                    cr.set_source_rgba(*self.pal.level_start)
            else:
                cr.set_source_rgba(*track, 0.55)
            cr.rectangle(i * (sw + gap), 0, sw, h)
            cr.fill()
        if self.peak_db is not None and top > 0:
            x = min(w - 2, top * w)
            cr.set_source_rgba(*self.pal.text)
            cr.rectangle(x, 0, 1.5, h)
            cr.fill()
        return False


def scale_row(pal, value, above100=False):
    row = hbox(8)
    mute = Gtk.Button.new_from_icon_name("audio-volume-muted-symbolic", Gtk.IconSize.BUTTON)
    mute.set_relief(Gtk.ReliefStyle.NONE)
    row.pack_start(mute, False, False, 0)
    scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 150 if above100 else 100, 1)
    scale.set_value(value)
    scale.set_draw_value(False)
    scale.set_hexpand(True)
    row.pack_start(scale, True, True, 0)
    row.pack_start(label(f"{int(value)}%", "value"), False, False, 0)
    return row


def device_icon(icon_name, size=Gtk.IconSize.DIALOG):
    img = Gtk.Image.new_from_icon_name(icon_name, size)
    img.set_valign(Gtk.Align.CENTER)
    return img


def connector_row(device):
    row = hbox(6)
    row.pack_start(label("Connector:", "muted"), False, False, 0)
    combo = Gtk.ComboBoxText()
    for c in device["connectors"]:
        combo.append_text(c)
    combo.set_active(0)
    row.pack_start(combo, False, False, 0)
    return row


# ---------------------------------------------------------------- the prototype
class Prototype:
    def __init__(self, pal, page):
        self.pal = pal
        self.win = Gtk.Window(title="Spaced Sound Manager")
        self.win.set_default_size(900, 680)
        self.win.set_size_request(720, 540)
        self.win.connect("destroy", Gtk.main_quit)

        bar = Gtk.HeaderBar()
        bar.set_show_close_button(True)
        bar.set_title("Spaced Sound Manager")
        bar.set_subtitle("4 outputs · 2 microphones · sound is working")
        self.win.set_titlebar(bar)

        refresh = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
        refresh.set_tooltip_text("Look for changes now")
        bar.pack_end(refresh)
        about = Gtk.Button.new_from_icon_name("help-about-symbolic", Gtk.IconSize.BUTTON)
        about.set_tooltip_text("About Spaced Sound Manager")
        bar.pack_end(about)

        outer = vbox(10)
        outer.set_margin_start(14)
        outer.set_margin_end(14)
        outer.set_margin_top(10)
        outer.set_margin_bottom(10)
        self.win.add(outer)

        switcher = Gtk.StackSwitcher()
        switcher.set_halign(Gtk.Align.CENTER)
        outer.pack_start(switcher, False, False, 0)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.NONE)
        switcher.set_stack(self.stack)
        for name in PAGES:
            self.stack.add_titled(self.page(name), name, name.capitalize())
        outer.pack_start(self.stack, True, True, 0)

        status = label("Sound goes to the LG monitor. To listen on the speakers "
                       "instead, pick them above.", "hint")
        outer.pack_start(status, False, False, 0)
        self.win.show_all()
        self.stack.set_visible_child_name(page)

    # ------------------------------------------------------------- pages
    def page(self, name):
        return getattr(self, "_" + name)()

    def _output(self):
        box = vbox(10)
        sel = OUTPUTS[0]
        card = card_box(8)
        head = hbox(10)
        head.pack_start(device_icon(sel["icon"]), False, False, 0)
        col = vbox(2)
        col.pack_start(label(sel["name"], "card-title"), False, False, 0)
        col.pack_start(label(sel["kind"], "muted"), False, False, 0)
        head.pack_start(col, True, True, 0)
        head.pack_start(Meter(self.pal, sel["levels"], sel["peak"]), False, False, 0)
        card.pack_start(head, False, False, 0)
        card.pack_start(connector_row(sel), False, False, 0)
        card.pack_start(scale_row(self.pal, sel["volume"]), False, False, 0)
        actions = hbox(8)
        test = Gtk.Button(label="Test sound")
        actions.pack_start(test, False, False, 0)
        use = Gtk.Button(label="Make this the one apps use")
        use.get_style_context().add_class("suggested")
        actions.pack_start(use, False, False, 0)
        card.pack_start(actions, False, False, 0)
        box.pack_start(card, False, False, 0)

        for d in OUTPUTS[1:]:
            row = hbox(10)
            row.get_style_context().add_class("card")
            row.pack_start(device_icon(d["icon"], Gtk.IconSize.BUTTON), False, False, 0)
            col = vbox(2)
            col.set_valign(Gtk.Align.CENTER)
            col.pack_start(label(d["name"], "value"), False, False, 0)
            col.pack_start(label(d["kind"] + ("  ·  " + d["raw"] if d["raw"] else ""), "muted"),
                           False, False, 0)
            row.pack_start(col, True, True, 0)
            row.pack_start(Meter(self.pal, d["levels"], d["peak"], width=110), False, False, 0)
            btn = Gtk.Button(label="Muted" if d["muted"] else "Use")
            btn.set_valign(Gtk.Align.CENTER)
            row.pack_start(btn, False, False, 0)
            box.pack_start(row, False, False, 0)
        return box

    def _input(self):
        box = vbox(10)
        sel = INPUTS[0]
        card = card_box(8)
        head = hbox(10)
        head.pack_start(device_icon(sel["icon"]), False, False, 0)
        col = vbox(2)
        col.pack_start(label(sel["name"], "card-title"), False, False, 0)
        col.pack_start(label(sel["kind"], "muted"), False, False, 0)
        head.pack_start(col, True, True, 0)
        head.pack_start(Meter(self.pal, sel["levels"], sel["peak"]), False, False, 0)
        card.pack_start(head, False, False, 0)
        card.pack_start(scale_row(self.pal, sel["volume"]), False, False, 0)
        actions = hbox(8)
        actions.pack_start(Gtk.Button(label="Show my microphone level"), False, False, 0)
        use = Gtk.Button(label="Make this the one apps record from")
        use.get_style_context().add_class("suggested")
        actions.pack_start(use, False, False, 0)
        card.pack_start(actions, False, False, 0)
        box.pack_start(card, False, False, 0)

        for d in INPUTS[1:]:
            row = hbox(10)
            row.get_style_context().add_class("card")
            row.pack_start(device_icon(d["icon"], Gtk.IconSize.BUTTON), False, False, 0)
            col = vbox(2)
            col.set_valign(Gtk.Align.CENTER)
            col.pack_start(label(d["name"], "value"), False, False, 0)
            col.pack_start(label(d["kind"], "muted"), False, False, 0)
            row.pack_start(col, True, True, 0)
            row.pack_start(Meter(self.pal, d["levels"], d["peak"], width=110), False, False, 0)
            btn = Gtk.Button(label="Use")
            btn.set_valign(Gtk.Align.CENTER)
            row.pack_start(btn, False, False, 0)
            box.pack_start(row, False, False, 0)
        box.pack_start(label("Your microphone is the Blue Yeti. If an app records silence, "
                             "check the app's own microphone setting.", "hint"),
                       False, False, 0)
        return box

    def _applications(self):
        box = vbox(10)
        card = card_box(8)
        card.pack_start(label("Playing", "card-title"), False, False, 0)
        for app in [a for a in APPS if a["group"] == "Playing"]:
            card.pack_start(self._app_row(app), False, False, 0)
        box.pack_start(card, False, False, 0)
        card = card_box(8)
        card.pack_start(label("Recording", "card-title"), False, False, 0)
        for app in [a for a in APPS if a["group"] == "Recording"]:
            card.pack_start(self._app_row(app), False, False, 0)
        box.pack_start(card, False, False, 0)
        box.pack_start(label("An app too quiet? Set its own slider here; it never changes "
                             "your other sounds.", "hint"), False, False, 0)
        return box

    def _app_row(self, app):
        row = hbox(8)
        row.pack_start(device_icon(app["icon"], Gtk.IconSize.BUTTON), False, False, 0)
        col = vbox(2)
        col.set_valign(Gtk.Align.CENTER)
        col.pack_start(label(app["name"], "value"), False, False, 0)
        col.pack_start(label("→ " + app["route"], "muted"), False, False, 0)
        row.pack_start(col, True, True, 0)
        row.pack_start(Meter(self.pal, app["levels"], None, width=110), False, False, 0)
        row.pack_start(scale_row(self.pal, app["volume"]), False, False, 0)
        move = Gtk.Button(label="Move to…")
        move.set_valign(Gtk.Align.CENTER)
        row.pack_start(move, False, False, 0)
        return row

    def _effects(self):
        box = vbox(10)
        card = card_box(8)
        card.pack_start(label("Sounds when things happen", "card-title"), False, False, 0)
        card.pack_start(Gtk.CheckButton(label="Play sounds when things happen"), False, False, 0)
        card.pack_start(Gtk.CheckButton(label="Play sounds for typing and clicks"), False, False, 0)
        row = hbox(6)
        row.pack_start(label("Sound theme:", "muted"), False, False, 0)
        combo = Gtk.ComboBoxText()
        for t in ("freedesktop", "No sounds", "Custom"):
            combo.append_text(t)
        combo.set_active(0)
        row.pack_start(combo, False, False, 0)
        card.pack_start(row, False, False, 0)
        box.pack_start(card, False, False, 0)

        card = card_box(8)
        card.pack_start(label("Alert sound", "card-title"), False, False, 0)
        tree = Gtk.TreeView(model=Gtk.ListStore(str, str, bool))
        model = tree.get_model()
        for name, kind, on in (("Default", "From theme", True),
                               ("Sound", "Built-in", False),
                               ("Glass", "Built-in", False),
                               ("Pop", "Built-in", False)):
            model.append([name, kind, on])
        col = Gtk.TreeViewColumn("Name", Gtk.CellRendererText(), text=0)
        tree.append_column(col)
        tree.append_column(Gtk.TreeViewColumn("Type", Gtk.CellRendererText(), text=1))
        sw = Gtk.CellRendererToggle()
        tree.append_column(Gtk.TreeViewColumn("", sw, active=2))
        card.pack_start(tree, False, False, 0)
        actions = hbox(8)
        actions.pack_start(Gtk.Button(label="Test"), False, False, 0)
        actions.pack_start(label("Alert volume", "muted"), False, False, 0)
        actions.pack_start(scale_row(self.pal, 70), True, True, 0)
        card.pack_start(actions, False, False, 0)
        card.pack_start(Gtk.CheckButton(label="Allow volume above 100 %"), False, False, 0)
        box.pack_start(card, False, False, 0)
        box.pack_start(label("Event sounds are played by your desktop, not by this app.",
                             "hint"), False, False, 0)
        return box

    def _advanced(self):
        box = vbox(10)
        card = card_box(8)
        card.pack_start(label("Cards and profiles", "card-title"), False, False, 0)
        for name, raw, profile in (
                ("LG monitor (HDMI on RTX 4070 Ti SUPER)",
                 "alsa_card.pci-0000_01_00.1 · HDA NVidia", "Digital Stereo (HDMI) Output"),
                ("Speakers (onboard audio)",
                 "alsa_card.pci-0000_00_1f.3 · HD-Audio Generic", "Analog Stereo duplex"),
                ("Blue Yeti microphone (USB)",
                 "alsa_card.usa-BLUE_MICROPHONE", "Input only - mono")):
            row = hbox(8)
            col = vbox(2)
            col.pack_start(label(name, "value"), False, False, 0)
            col.pack_start(label(raw, "muted"), False, False, 0)
            row.pack_start(col, True, True, 0)
            combo = Gtk.ComboBoxText()
            for p in (profile, "Off"):
                combo.append_text(p)
            combo.set_active(0)
            row.pack_start(combo, False, False, 0)
            card.pack_start(row, False, False, 0)
        card.pack_start(label("Changing this turns the sound off for a second and moves "
                             "sounds that are playing onto the new setup.", "hint"),
                       False, False, 0)
        box.pack_start(card, False, False, 0)

        card = card_box(8)
        card.pack_start(label("Speaker testing", "card-title"), False, False, 0)
        card.pack_start(label("Speaker testing — press each speaker's button as you hear it.",
                             "muted"), False, False, 0)
        row = hbox(8)
        for side in ("Left", "Right", "Center", "Sub"):
            row.pack_start(Gtk.Button(label=side), False, False, 0)
        card.pack_start(row, False, False, 0)
        box.pack_start(card, False, False, 0)

        card = card_box(8)
        card.pack_start(label("Trouble", "card-title"), False, False, 0)
        card.pack_start(Gtk.Button(label="Open the old Sound Preferences"), False, False, 0)
        card.pack_start(label("Spaced 11.26.4 does not install an equaliser with the "
                             "PulseAudio release.", "hint"), False, False, 0)
        box.pack_start(card, False, False, 0)
        return box


def play_test_sound(args):
    """Design placeholder: would call paplay. Refuses unless a human clicked."""
    if "--i-was-clicked" not in sys.argv:
        return "refused: no sound without a click"
    return "would run: paplay /usr/share/sounds/spaced/sound-test.wav"


# ---------------------------------------------------------------- capture
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--capture", choices=PAGES)
    ap.add_argument("--palette", choices=["dark", "light"], default="dark")
    ap.add_argument("--out")
    ap.add_argument("--preview", action="store_true", help="read-only: controls insensitive")
    ap.add_argument("--fake", action="store_true", help="use the fake bigboy data (always)")
    ap.add_argument("--i-was-clicked", action="store_true",
                    help="allow the test-sound path (never set by the mockups)")
    args = ap.parse_args()

    pal = DARK if args.palette == "dark" else LIGHT
    provider = Gtk.CssProvider()
    provider.load_from_data(css(pal).encode())
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)

    page = args.capture or "output"
    proto = Prototype(pal, page)
    if args.preview:
        for w in proto.win.get_children():
            w.sensitive = False

    if not args.capture:
        Gtk.main()
        return 0

    GLib.timeout_add_seconds(1, Gtk.main_quit)
    Gtk.main()

    gdk_window = proto.win.get_window()
    if gdk_window is None:
        print("FAIL: no gdk window", file=sys.stderr)
        return 1
    w, h = proto.win.get_size()
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
    with open(args.out, "wb") as fh:
        fh.write(data)
    print(f"wrote {args.out} ({w}x{h})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
