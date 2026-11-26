#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Spaced Sound Manager — the approved app that replaces Sound Preferences.

Builds the five pages (Output · Input · Applications · Effects · Advanced) in the
family look rhY approved on 2026-11-26 (docs/design/sound-manager + the
FAMILY-LOOK.md token/icon rules). It talks to the sound server only through the
spaced_sound backend (``pactl`` / the PulseAudio native protocol — the same one
PipeWire implements), never ALSA directly and never a PipeWire-only control.

Colours follow the desktop theme exactly like Spaced Monitor
(spaced_monitor/theme.py): the same layout uses dark or light tokens, the accent
and pill colours never change, and nothing hard-codes a dark-only look. Tokens
are defined once in :class:`Palette` and used everywhere.

Safety carried from the design: it never plays a sound or opens a microphone
unless the user clicked (DESIGN.md §5.1/§7), all meters and timers stop while the
window is hidden, and no microphone monitor is opened unless the caller is on the
Input page and the listening button was pressed (the microphone-listening guard).
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, Pango

_HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, "/usr/lib/spaced-linux")
sys.path.insert(0, _HERE)
import spaced_sound  # noqa: E402
from spaced_sound import Backend, Device  # noqa: E402
import spaced_family_style as family  # noqa: E402

# Icons/logo live beside the install prefix: usr/share/spaced-sound-manager when
# installed, overlays/usr/share/spaced-sound-manager when run from a source tree.
ICON_DIR = os.path.normpath(os.path.join(_HERE, "..", "..", "share",
                                         "spaced-sound-manager"))
if not os.path.isdir(ICON_DIR):
    ICON_DIR = "/usr/share/spaced-sound-manager"
PAGES = ["output", "input", "applications", "effects", "advanced"]
TAB_LABEL = {
    "output": "Output", "input": "Input", "applications": "Applications",
    "effects": "Effects", "advanced": "Advanced",
}
# Line icons shipped in the repo (FAMILY-LOOK: no icon-theme or network
# lookup); one consistent stroke width, tinted with the theme text colour.
KIND_ICON = {
    "speakers": "speakers", "headphones": "headphones",
    "microphone": "microphone", "webcam": "webcam",
    "hdmi_output": "hdmi_output", "digital": "digital", None: "generic",
}


# --------------------------------------------------------------- colour tokens
# The navy family tokens live in spaced_family_style so the GPU and Sound
# managers never drift; Palette/DARK/LIGHT are that module's. Palette carries
# bg (window), meter_track and the level_* colours this app reads.
Palette = family.Palette
DARK = family.DARK
LIGHT = family.LIGHT


def _css_colour(c):
    return family.css_colour(c)


def _rgba(c, a):
    return family.rgba(c, a)


def css(pal: Palette) -> str:
    p = {k: _css_colour(getattr(pal, k)) for k in
         ("bg", "band", "card", "border", "text", "muted", "accent",
          "accent_ink", "ok", "warn", "ai", "off")}
    return f"""
window, .background {{ background-color: {p['bg']}; color: {p['text']}; }}
/* One navy page background behind the heading and cards (issue #429 review,
   S3): the stack/box paint the family bg, never the GTK theme's grey base. */
stack, stack > box, box.page {{ background-color: {p['bg']}; }}
.band {{ background-color: {p['band']}; }}
.band-title {{ font-weight: bold; font-size: 20px; color: {p['text']}; }}
.band-tagline {{ font-size: 12px; color: {p['muted']}; }}
.logo-divider {{ background-color: {p['border']}; min-width: 1px; }}
button.icon-btn {{ border-radius: 8px; border: 1px solid {p['border']};
  background-color: {p['card']}; color: {p['text']}; padding: 5px 9px;
  min-height: 0; background-image: none; }}
button.icon-btn:hover {{ background-color: {p['border']}; }}
.tabbar {{ border-bottom: 1px solid {p['border']}; }}
button.tab {{ background-color: transparent; background-image: none;
  border: none; border-radius: 999px; color: {p['muted']};
  padding: 5px 12px; min-height: 0; }}
button.tab:hover {{ color: {p['text']}; }}
button.tab label {{ color: {p['muted']}; }}
/* Active tab: a filled accent pill with white text (issue #429 review, S1).
   The label follows the button colour, so it is never muted-on-accent. The
   fill is the darker accent_ink so white text clears WCAG 4.5. */
button.tab.active {{ background-color: {p['accent_ink']}; color: #ffffff; }}
button.tab.active label {{ color: #ffffff; }}
.page-title {{ font-weight: bold; font-size: 28px; color: {p['text']}; }}
.page-sub {{ font-size: 13px; color: {p['muted']}; }}
.accent-bar {{ background-color: {p['accent']}; min-width: 4px;
  border-radius: 2px; }}
.card {{ background-color: {p['card']}; border: 1px solid {p['border']};
  border-radius: 12px; padding: 12px; color: {p['text']}; }}
.card.primary {{ border: 1px solid {p['accent']};
  box-shadow: 0 0 14px {_rgba(pal.accent, 0.35)}; }}
.divider {{ background-color: {p['border']}; min-height: 1px; }}
.vdiv {{ background-color: {p['border']}; min-width: 1px; }}
.dev-name {{ font-weight: bold; font-size: 22px; color: {p['text']}; }}
.dev-name-sm {{ font-weight: bold; font-size: 15px; color: {p['text']}; }}
.detail {{ font-size: 12px; color: {p['muted']}; }}
.raw {{ font-size: 11px; color: {p['muted']}; font-style: italic; }}
.small-label {{ font-size: 11px; color: {p['muted']}; }}
/* Status pills: tinted translucent fill + coloured border + the theme text
   colour (issue #429 review, S1) - never solid colour-on-same-colour, which is
   how "Default output" came out green-on-green. */
.pill {{ border-radius: 999px; padding: 2px 10px; font-size: 11px;
  color: {p['text']}; }}
.pill label {{ color: {p['text']}; }}
.pill.ok {{ background-color: {_rgba(pal.ok, 0.18)}; border: 1px solid {p['ok']}; }}
.pill.warn {{ background-color: {_rgba(pal.warn, 0.18)}; border: 1px solid {p['warn']}; }}
.pill.off {{ background-color: {_rgba(pal.off, 0.20)}; border: 1px solid {p['off']}; }}
.pill.ai {{ background-color: {_rgba(pal.ai, 0.20)}; border: 1px solid {p['ai']}; }}
.pill.value {{ background-color: {p['card']}; border: 1px solid {p['border']}; }}
.footer {{ border-top: 1px solid {p['border']}; }}
.dot-ok {{ background-color: {p['ok']}; min-width: 8px; min-height: 8px;
  border-radius: 50%; }}
.dot-warn {{ background-color: {p['warn']}; min-width: 8px; min-height: 8px;
  border-radius: 50%; }}
/* Footer link (issue #429 review, S7): accent text, no grey box. */
button.link {{ background-color: transparent; background-image: none;
  border: none; color: {p['accent']}; padding: 2px 4px; }}
button.link:hover {{ background-color: transparent; color: {p['accent']}; }}
button.outline {{ border: 1px solid {p['border']}; border-radius: 8px;
  background-image: none; background-color: {p['card']}; color: {p['text']};
  padding: 4px 10px; min-height: 0; }}
button.primary {{ border: none; border-radius: 8px; background-image: none;
  background-color: {p['accent_ink']}; color: #ffffff; padding: 4px 12px;
  min-height: 0; }}
list, row {{ background-color: {p['card']}; color: {p['text']}; border: none; }}
/* Connector dropdown: family navy, readable in every theme (11.26.4 review). */
combobox button, combobox box.linked button {{ background-image: none;
  background-color: {p['bg']}; color: {p['text']}; border: 1px solid {p['border']};
  border-radius: 8px; box-shadow: none; text-shadow: none; }}
combobox button label, combobox button arrow, combobox cellview {{ color: {p['text']}; }}
button.link {{ box-shadow: none; outline: none; }}
combobox, combobox button {{ background-color: {p['card']}; color: {p['text']};
  border: 1px solid {p['border']}; border-radius: 6px; }}
combobox window, combobox row, combobox list {{ background-color: {p['card']};
  color: {p['text']}; }}
"""


def resolve_palette(name: str) -> Palette:
    return family.palette_for(name == "dark")


# ------------------------------------------------------------------ widgets
def _lbl(text, cls="detail", wrap=False):
    lab = Gtk.Label(label=text)
    lab.get_style_context().add_class(cls)
    lab.set_xalign(0)
    if wrap:
        lab.set_line_wrap(True)
        lab.set_max_width_chars(60)
    return lab


def _dot(cls):
    d = Gtk.Box()
    d.get_style_context().add_class(cls)
    d.set_valign(Gtk.Align.CENTER)
    return d


def _tint(pixbuf, colour):
    """Recolour a line icon to the theme text colour, keeping the alpha mask."""
    r = int(colour[0] * 255)
    g = int(colour[1] * 255)
    b = int(colour[2] * 255)
    src = pixbuf.get_pixels()
    channels = pixbuf.get_n_channels()
    rowstride = pixbuf.get_rowstride()
    out = bytearray(src)
    for y in range(pixbuf.get_height()):
        base = y * rowstride
        for x in range(pixbuf.get_width()):
            off = base + x * channels
            if channels >= 4 and out[off + 3] == 0:
                continue
            out[off] = r
            out[off + 1] = g
            out[off + 2] = b
    return GdkPixbuf.Pixbuf.new_from_data(
        bytes(out), pixbuf.get_colorspace(), pixbuf.get_has_alpha(), 8,
        pixbuf.get_width(), pixbuf.get_height(), rowstride)


def _line_icon(pal, name, px=24):
    """A shipped line icon tinted with the theme's text colour (no theme lookup)."""
    path = "%s/icons/%s.svg" % (ICON_DIR, name)
    try:
        pb = GdkPixbuf.Pixbuf.new_from_file_at_size(path, px, px)
        pb = _tint(pb, pal.text)
        return Gtk.Image.new_from_pixbuf(pb)
    except Exception:
        img = Gtk.Image.new_from_icon_name("image-x-generic-symbolic",
                                           Gtk.IconSize.BUTTON)
        return img


def _logo_image(px=40):
    try:
        pb = GdkPixbuf.Pixbuf.new_from_file_at_size("%s/planet.svg" % ICON_DIR,
                                                    px, px)
        return Gtk.Image.new_from_pixbuf(pb)
    except Exception:
        return Gtk.Image.new_from_file("%s/planet.svg" % ICON_DIR)


def _art_image():
    return Gtk.Image.new_from_file("%s/band-art.svg" % ICON_DIR)


class Meter(Gtk.DrawingArea):
    """Segmented level meter; em dash on no data, never a fake bar."""

    def __init__(self, pal, levels, peak_db=None, width=150, height=14):
        super().__init__()
        self.pal, self.levels, self.peak_db = pal, levels, peak_db
        self.set_size_request(width, height)
        self.connect("draw", self._draw)

    def set_levels(self, levels):
        self.levels = levels
        self.queue_draw()

    def _draw(self, _w, cr):
        alloc = self.get_allocation()
        w, h = alloc.width, alloc.height
        segs, gap = 14, 2
        sw = (w - gap * (segs - 1)) / segs
        levels = self.levels or ()
        top = max(levels) if levels else 0.0
        for i in range(segs):
            frac = (i + 1) / segs
            if frac <= top:
                if frac > 0.86:
                    cr.set_source_rgba(*self.pal.level_peak)
                elif frac > 0.62:
                    cr.set_source_rgba(*self.pal.level_mid)
                else:
                    cr.set_source_rgba(*self.pal.level_start)
            else:
                cr.set_source_rgba(*self.pal.meter_track, 0.55)
            cr.rectangle(i * (sw + gap), 0, sw, h)
            cr.fill()
        if self.peak_db is not None and top > 0:
            x = min(w - 2, top * w)
            cr.set_source_rgba(*self.pal.text)
            cr.rectangle(x, 0, 1.5, h)
            cr.fill()
        return False


def _scale(value, above100=False):
    scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0,
                                     150 if above100 else 100, 1)
    scale.set_value(value)
    scale.set_draw_value(False)
    scale.set_hexpand(True)
    return scale


def _status_pill(text, kind):
    box = Gtk.Box()
    box.get_style_context().add_class("pill")
    box.get_style_context().add_class(kind)
    box.pack_start(_lbl(text, "detail"), False, False, 0)
    return box


def _value_pill(text):
    """A small neutral pill for a value such as the volume percentage (S6)."""
    box = Gtk.Box()
    box.get_style_context().add_class("pill")
    box.get_style_context().add_class("value")
    box.pack_start(_lbl(text, "detail"), False, False, 0)
    return box


# ------------------------------------------------------------------ the app
class SoundManager:
    def __init__(self, backend: Backend, pal: Palette, preview=False):
        self.backend = backend
        self.pal = pal
        self.preview = preview
        self.current_page = "output"
        self._listening_raw = None
        self._tick_id = None
        self._visible = True
        self.win = Gtk.Window(title="Spaced Sound Manager")
        self.win.set_default_size(900, 680)
        self.win.set_size_request(720, 540)
        self.win.connect("destroy", Gtk.main_quit)
        self.win.connect("window-state-event", self._on_state)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.win.add(outer)
        outer.pack_start(self._header_band(), False, False, 0)
        outer.pack_start(self._tab_bar(), False, False, 0)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        body.set_margin_start(16)
        body.set_margin_end(16)
        body.set_margin_top(14)
        body.set_margin_bottom(6)
        outer.pack_start(body, True, True, 0)
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.NONE)
        for name in PAGES:
            self.stack.add_titled(self._page(name), name, TAB_LABEL[name])
        body.pack_start(self.stack, True, True, 0)
        outer.pack_start(self._footer(), False, False, 0)
        if self.preview:
            self._insensitive(outer)

    # ----- header band -----------------------------------------------------
    def _header_band(self):
        band = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        band.get_style_context().add_class("band")
        band.set_margin_start(16)
        band.set_margin_end(16)
        band.set_margin_top(12)
        band.set_margin_bottom(8)

        logo = _logo_image(40)
        band.pack_start(logo, False, False, 0)

        div = Gtk.Box()
        div.get_style_context().add_class("logo-divider")
        div.set_size_request(1, 40)
        band.pack_start(div, False, False, 0)

        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        col.pack_start(_lbl("Spaced Sound Manager", "band-title"), False,
                       False, 0)
        col.pack_start(_lbl("Your sound, beautifully connected.", "band-tagline"),
                       False, False, 0)
        band.pack_start(col, False, False, 0)

        # The faint space art is drawn by the band's own navy colour
        # (FAMILY-LOOK §1: "a pure gradient if simpler"). A shipped SVG here
        # rendered as a broken white image in the middle of the header (issue
        # #429 review, S2), so the band keeps just the navy fill.
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        band.pack_start(spacer, True, True, 0)

        info = _line_icon(self.pal, "info", 18)
        info_btn = Gtk.Button()
        info_btn.add(info)
        info_btn.get_style_context().add_class("icon-btn")
        info_btn.set_tooltip_text("About Spaced Sound Manager")
        band.pack_start(info_btn, False, False, 0)
        refresh = _line_icon(self.pal, "refresh", 18)
        refresh_btn = Gtk.Button()
        refresh_btn.add(refresh)
        refresh_btn.get_style_context().add_class("icon-btn")
        refresh_btn.set_tooltip_text("Look for changes now")
        refresh_btn.connect("clicked", self._reload)
        band.pack_start(refresh_btn, False, False, 0)
        return band

    # ----- tab bar ---------------------------------------------------------
    def _tab_bar(self):
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        bar.get_style_context().add_class("tabbar")
        bar.set_margin_start(16)
        bar.set_margin_end(16)
        bar.set_halign(Gtk.Align.CENTER)
        self._tab_buttons = {}
        for name in PAGES:
            btn = Gtk.Button()
            inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            inner.pack_start(_line_icon(self.pal, name, 16), False, False, 0)
            inner.pack_start(_lbl(TAB_LABEL[name], "detail"), False, False, 0)
            btn.add(inner)
            btn.get_style_context().add_class("tab")
            btn.connect("clicked", self._switch_page, name)
            bar.pack_start(btn, False, False, 0)
            self._tab_buttons[name] = btn
        self._set_active_tab("output")
        return bar

    def _set_active_tab(self, name):
        for n, btn in self._tab_buttons.items():
            ctx = btn.get_style_context()
            if n == name:
                ctx.add_class("active")
            else:
                ctx.remove_class("active")

    def _switch_page(self, _btn, name):
        self.current_page = name
        self.stack.set_visible_child_name(name)
        self._set_active_tab(name)
        self._update_meters()

    # ----- page heading ----------------------------------------------------
    def _page_heading(self, title, subtitle):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        bar = Gtk.Box()
        bar.get_style_context().add_class("accent-bar")
        bar.set_size_request(4, 40)
        bar.set_valign(Gtk.Align.CENTER)
        row.pack_start(bar, False, False, 0)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        col.set_valign(Gtk.Align.CENTER)
        col.pack_start(_lbl(title, "page-title"), False, False, 0)
        sub = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        sub.pack_start(_dot("dot-ok"), False, False, 0)
        sub.pack_start(_lbl(subtitle, "page-sub"), False, False, 0)
        col.pack_start(sub, False, False, 0)
        row.pack_start(col, True, True, 0)
        return row

    # ----- footer ----------------------------------------------------------
    def _footer(self):
        foot = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        foot.get_style_context().add_class("footer")
        foot.set_margin_start(16)
        foot.set_margin_end(16)
        foot.set_margin_top(8)
        foot.set_margin_bottom(10)
        foot.pack_start(_dot("dot-ok"), False, False, 0)
        foot.pack_start(_lbl("Sound is working", "page-sub"), False, False, 0)
        link = Gtk.Button(label="Manage app volumes")
        link.get_style_context().add_class("link")
        link.connect("clicked", self._switch_page, "applications")
        foot.pack_end(link, False, False, 0)
        return foot

    # ----- pages -----------------------------------------------------------
    def _page(self, name):
        return getattr(self, "_page_" + name)()

    def _devices(self):
        return self.backend.devices()

    def _outputs(self):
        return [d for d in self._devices() if not d.is_input]

    def _inputs(self):
        return [d for d in self._devices() if d.is_input]

    def _page_output(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        outputs = self._outputs()
        default = next((d for d in outputs if d.is_default),
                       outputs[0] if outputs else None)
        n_out, n_in = len(outputs), len(self._inputs())
        box.pack_start(self._page_heading(
            "Sound output",
            "%d outputs · %d microphones · Audio is working" % (n_out, n_in)),
            False, False, 0)
        if default:
            box.pack_start(self._big_card(default), False, False, 0)
        if len(outputs) > 1:
            box.pack_start(_lbl("Other outputs", "small-label"), False,
                           False, 0)
            for d in outputs:
                if d is not default:
                    box.pack_start(self._compact_row(d, is_input=False),
                                   False, False, 0)
        box.pack_start(_lbl(
            "Sound goes to the %s. To listen on the speakers instead, pick "
            "them above." % (default.friendly if default else "monitor"),
            "detail"), False, False, 0)
        return box

    def _page_input(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        inputs = self._inputs()
        default = next((d for d in inputs if d.is_default),
                       inputs[0] if inputs else None)
        box.pack_start(self._page_heading(
            "Sound input",
            "%d microphones · Audio is working" % len(inputs)), False, False, 0)
        if default:
            box.pack_start(self._big_card(default), False, False, 0)
        for d in inputs:
            if d is not default:
                box.pack_start(self._compact_row(d, is_input=True), False,
                               False, 0)
        box.pack_start(_lbl(
            "Your microphone is the %s. If an app records silence, check the "
            "app's own microphone setting." % (default.friendly if default else
                                               "default"),
            "detail"), False, False, 0)
        return box

    def _page_applications(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.pack_start(self._page_heading("Applications",
                                          "Per-app volume, kept apart from "
                                          "your other sounds"), False, False, 0)
        streams = self.backend.streams()
        for group in ("playing", "recording"):
            items = [s for s in streams if s["kind"] == group]
            card = self._card()
            card.pack_start(_lbl("Playing" if group == "playing" else
                                 "Recording", "dev-name-sm"), False, False, 0)
            if not items:
                card.pack_start(_lbl(
                    "Nothing is playing or recording sound right now.",
                    "detail"), False, False, 0)
            for s in items:
                card.pack_start(self._app_row(s), False, False, 0)
            box.pack_start(card, False, False, 0)
        box.pack_start(_lbl("An app too quiet? Set its own slider here; it "
                            "never changes your other sounds.", "detail"),
                       False, False, 0)
        return box

    def _page_effects(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.pack_start(self._page_heading("Effects",
                                          "Event sounds your desktop plays"),
                       False, False, 0)
        card = self._card()
        card.pack_start(_lbl("Sounds when things happen", "dev-name-sm"),
                        False, False, 0)
        card.pack_start(Gtk.CheckButton(label="Play sounds when things happen"),
                        False, False, 0)
        card.pack_start(Gtk.CheckButton(
            label="Play sounds for typing and clicks"), False, False, 0)
        box.pack_start(card, False, False, 0)
        card = self._card()
        card.pack_start(_lbl("Alert sound", "dev-name-sm"), False, False, 0)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.pack_start(_lbl("Sound theme:", "detail"), False, False, 0)
        combo = Gtk.ComboBoxText()
        for t in ("freedesktop", "No sounds", "Custom"):
            combo.append_text(t)
        combo.set_active(0)
        row.pack_start(combo, False, False, 0)
        card.pack_start(row, False, False, 0)
        card.pack_start(Gtk.CheckButton(
            label="Allow volume above 100 %"), False, False, 0)
        box.pack_start(card, False, False, 0)
        box.pack_start(_lbl("Event sounds are played by your desktop, not by "
                            "this app.", "detail"), False, False, 0)
        return box

    def _page_advanced(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.pack_start(self._page_heading("Advanced",
                                          "Raw sound-server names, shown once"),
                       False, False, 0)
        card = self._card()
        card.pack_start(_lbl("Cards and profiles", "dev-name-sm"), False,
                        False, 0)
        for d in self._devices():
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
            col.pack_start(_lbl(d.friendly, "dev-name-sm"), False, False, 0)
            # the ONLY screen where raw PulseAudio/ALSA strings appear (§10)
            col.pack_start(_lbl(d.raw, "raw"), False, False, 0)
            row.pack_start(col, True, True, 0)
            combo = Gtk.ComboBoxText()
            for p in (d.profile or "Analog Stereo", "Off"):
                combo.append_text(p)
            combo.set_active(0)
            row.pack_start(combo, False, False, 0)
            card.pack_start(row, False, False, 0)
        card.pack_start(_lbl("Changing this turns the sound off for a second "
                             "and moves sounds that are playing onto the new "
                             "setup.", "detail"), False, False, 0)
        box.pack_start(card, False, False, 0)
        card = self._card()
        card.pack_start(_lbl("Trouble", "dev-name-sm"), False, False, 0)
        card.pack_start(Gtk.Button(label="Open the old Sound Preferences"),
                        False, False, 0)
        card.pack_start(_lbl("Spaced 11.26.4 does not install an equaliser "
                             "with the PulseAudio release.", "detail"), False,
                        False, 0)
        box.pack_start(card, False, False, 0)
        return box

    # ----- card building ---------------------------------------------------
    def _card(self, primary=False):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.get_style_context().add_class("card")
        if primary:
            box.get_style_context().add_class("primary")
        return box

    def _big_card(self, d: Device):
        card = self._card(primary=True)
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        icon = _line_icon(self.pal, KIND_ICON.get(d.icon_kind, "generic"), 64)
        icon.set_valign(Gtk.Align.CENTER)
        head.pack_start(icon, False, False, 0)
        vdiv = Gtk.Box()
        vdiv.get_style_context().add_class("vdiv")
        vdiv.set_size_request(1, 56)
        head.pack_start(vdiv, False, False, 0)

        mid = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        name_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        # The big-card name is the short device name; the "(HDMI on RTX 4070
        # Ti SUPER)" tail lives on the detail line instead, so the name no
        # longer repeats the detail (issue #429 review, S4).
        short = d.friendly.split(" (")[0]
        name_row.pack_start(_lbl(short, "dev-name"), False, False, 0)
        pill = self._pill_for(d)
        if pill is not None:
            name_row.pack_start(pill, False, False, 0)
        mid.pack_start(name_row, False, False, 0)
        if d.icon_kind == "hdmi_output" and getattr(d, "gpu", ""):
            detail = "HDMI audio \u00b7 %s" % d.gpu
        else:
            detail = d.detail
        mid.pack_start(_lbl(detail, "detail"), False, False, 0)
        head.pack_start(mid, True, True, 0)

        meter_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        meter_col.set_valign(Gtk.Align.CENTER)
        meter_col.pack_start(_lbl("Audio activity", "small-label"), False,
                             False, 0)
        meter_col.pack_start(Meter(self.pal, d.levels, d.peak_db), False,
                             False, 0)
        head.pack_start(meter_col, False, False, 0)
        card.pack_start(head, False, False, 0)

        # mute button + "Volume" label + slider + percent pill (issue #429
        # review, S6).
        vol_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        mute = Gtk.Button()
        mute.add(_line_icon(self.pal, "mute" if d.muted else "unmute", 16))
        mute.get_style_context().add_class("outline")
        mute.connect("clicked", self._toggle_mute, d.raw)
        vol_row.pack_start(_lbl("Volume", "small-label"), False, False, 0)
        vol_row.pack_start(mute, False, False, 0)
        vol_row.pack_start(_scale(d.volume), True, True, 0)
        vol_row.pack_start(_value_pill("%d%%" % d.volume), False, False, 0)
        card.pack_start(vol_row, False, False, 0)

        if d.ports:
            conn = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            conn.pack_start(_lbl("Connector:", "detail"), False, False, 0)
            combo = Gtk.ComboBoxText()
            for port in d.ports:
                combo.append_text(port.name +
                                  (" (nothing plugged in)"
                                   if not port.available else ""))
            combo.set_active(0)
            conn.pack_start(combo, False, False, 0)
            card.pack_start(conn, False, False, 0)

        if d.is_input:
            card.pack_start(self._mic_guard_row(d), False, False, 0)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        test = Gtk.Button(label="Test sound")
        test.get_style_context().add_class("outline")
        test.connect("clicked", self._test_sound, d.raw)
        actions.pack_start(test, False, False, 0)
        dev_btn = Gtk.Button(label="Device settings")
        dev_btn.get_style_context().add_class("outline")
        actions.pack_start(dev_btn, False, False, 0)
        # The default card already IS the one apps use, so it does not offer to
        # make itself the default (issue #429 review, S5).
        if not d.is_default:
            make = Gtk.Button(
                label="Make this the one apps use" if not d.is_input
                else "Make this the one apps record from")
            make.get_style_context().add_class("primary")
            actions.pack_end(make, False, False, 0)
        card.pack_start(actions, False, False, 0)
        return card

    def _compact_row(self, d: Device, is_input):
        row = self._card()
        row.set_orientation(Gtk.Orientation.HORIZONTAL)
        icon = _line_icon(self.pal, KIND_ICON.get(d.icon_kind, "generic"), 28)
        icon.set_valign(Gtk.Align.CENTER)
        row.pack_start(icon, False, False, 0)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        col.set_valign(Gtk.Align.CENTER)
        col.pack_start(_lbl(d.friendly, "dev-name-sm"), False, False, 0)
        col.pack_start(_lbl(d.detail, "detail"), False, False, 0)
        row.pack_start(col, True, True, 0)
        if d.muted:
            row.pack_start(_status_pill("Muted", "warn"), False, False, 0)
        elif not d.available:
            row.pack_start(_status_pill("Disconnected", "off"), False, False, 0)
        row.pack_start(Meter(self.pal, d.levels, d.peak_db, width=90), False,
                       False, 0)
        btn = Gtk.Button(label="Unmute" if d.muted else "Use output")
        if not d.available and not d.muted:
            btn.set_sensitive(False)
        btn.get_style_context().add_class("outline")
        btn.set_valign(Gtk.Align.CENTER)
        btn.connect("clicked", self._use_device, d.raw, is_input)
        row.pack_start(btn, False, False, 0)
        return row

    def _app_row(self, s):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.pack_start(Gtk.Image.new_from_icon_name(
            s.get("icon", "application-x-executable-symbolic"),
            Gtk.IconSize.BUTTON), False, False, 0)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        col.set_valign(Gtk.Align.CENTER)
        col.pack_start(_lbl(s["name"], "dev-name-sm"), False, False, 0)
        col.pack_start(_lbl("→ " + s["route"], "detail"), False, False, 0)
        row.pack_start(col, True, True, 0)
        row.pack_start(Meter(self.pal, s["levels"], None, width=90), False,
                       False, 0)
        row.pack_start(_scale(s["volume"]), False, True, 0)
        row.set_size_request(200, -1)
        move = Gtk.Button(label="Move to…")
        move.get_style_context().add_class("outline")
        move.set_valign(Gtk.Align.CENTER)
        row.pack_start(move, False, False, 0)
        return row

    def _pill_for(self, d: Device):
        if d.muted:
            return _status_pill("Muted", "warn")
        if d.is_default:
            return _status_pill("Default output", "ok")
        if not d.available:
            return _status_pill("Disconnected", "off")
        return None

    # ----- microphone-listening guard (DESIGN.md §7) -----------------------
    def _mic_guard_row(self, d: Device):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn = Gtk.Button(label="Show my microphone level")
        btn.get_style_context().add_class("outline")
        btn.connect("clicked", self._toggle_mic_level, d.raw)
        row.pack_start(btn, False, False, 0)
        return row

    def _toggle_mic_level(self, _btn, raw):
        # The guard opens the microphone only on the Input page, on a click.
        if self._listening_raw:
            self._listening_raw = None
        else:
            self._listening_raw = raw
            if self.current_page == "input":
                self.backend.open_microphone_level(raw, on_input_page=True,
                                                   user_authorized=True)

    # ----- actions ---------------------------------------------------------
    def _use_device(self, _btn, raw, is_input):
        if is_input:
            self.backend.set_default_input(raw)
        else:
            self.backend.set_default_output(raw)
        self._reload()

    def _toggle_mute(self, _btn, raw):
        d = next((x for x in self._devices() if x.raw == raw), None)
        if d:
            self.backend.set_mute(raw, not d.muted)
            self._reload()

    def _test_sound(self, _btn, raw):
        # DESIGN.md §5.1: only ever plays on a click, never in --fake/--preview.
        if isinstance(self.backend, spaced_sound.FakeBackend) or self.preview:
            return  # renders and tests never play sound
        self._play_test_sound(raw)

    @staticmethod
    def _play_test_sound(raw):  # pragma: no cover - never reached in tests
        import subprocess
        subprocess.run(["paplay", "--device=%s.monitor" % raw,
                        "/usr/share/sounds/spaced/sound-test.wav"],
                       timeout=5, check=False)

    def _reload(self):
        # Rebuild the pages from the backend without leaking the old widgets.
        for name in list(PAGES):
            child = self.stack.get_child_by_name(name)
            if child is not None:
                self.stack.remove(child)
        for name in PAGES:
            self.stack.add_titled(self._page(name), name, TAB_LABEL[name])
        self.stack.show_all()
        self.stack.set_visible_child_name(self.current_page)
        self._set_active_tab(self.current_page)
        return True

    # ----- meters / timers (all stop while hidden) -------------------------
    def _start_timers(self):
        if self._tick_id is None:
            self._tick_id = GLib.timeout_add(2000, self._update_meters)

    def _stop_timers(self):
        if self._tick_id is not None:
            GLib.source_remove(self._tick_id)
            self._tick_id = None

    def _on_state(self, _w, event):
        # Stop every timer and meter while the window is minimized or hidden;
        # 0 work when closed (there is no daemon).
        new = event.new_window_state
        hidden = bool(new & Gdk.WindowState.ICONIFIED) or bool(
            new & Gdk.WindowState.WITHDRAWN)
        if hidden:
            self._visible = False
            self._stop_timers()
        else:
            self._visible = True
            self._start_timers()
        return False

    def _update_meters(self):
        # Meters only read while the Output/Input page is visible (FAMILY-LOOK).
        if self.current_page in ("output", "input") and self._visible:
            for area in self._meters():
                area.queue_draw()
        return True

    def _meters(self):
        found = []
        stack = [self.stack]
        while stack:
            w = stack.pop()
            if isinstance(w, Meter):
                found.append(w)
            if isinstance(w, Gtk.Container):
                stack.extend(w.get_children())
        return found

    def _insensitive(self, w):
        if isinstance(w, (Gtk.Button, Gtk.Scale, Gtk.ComboBoxText,
                          Gtk.CheckButton)):
            w.set_sensitive(False)
        if isinstance(w, Gtk.Container):
            for c in w.get_children():
                self._insensitive(c)

    def run(self):
        self.win.show_all()
        self._start_timers()
        Gtk.main()


# ------------------------------------------------------------------ capture
def _capture(app, page, out):
    app.win.show_all()
    app.stack.set_visible_child_name(page)
    app._set_active_tab(page)
    GLib.timeout_add(300, Gtk.main_quit)
    Gtk.main()
    gdk_window = app.win.get_window()
    if gdk_window is None:
        print("FAIL: no gdk window", file=sys.stderr)
        return 1
    w, h = app.win.get_size()
    pixbuf = Gdk.pixbuf_get_from_window(gdk_window, 0, 0, w, h)
    if pixbuf is None:
        print("FAIL: no pixbuf", file=sys.stderr)
        return 1
    ok, data = pixbuf.save_to_bufferv("png", [])
    if not ok:
        print("FAIL: save failed", file=sys.stderr)
        return 1
    with open(out, "wb") as fh:
        fh.write(data)
    print("wrote %s (%dx%d)" % (out, w, h))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--fake", action="store_true",
                    help="use the deterministic bigboy data (never real)")
    ap.add_argument("--preview", action="store_true",
                    help="read-only: every control is insensitive")
    ap.add_argument("--palette", choices=["dark", "light"], default="dark")
    ap.add_argument("--capture", choices=PAGES)
    ap.add_argument("--out")
    ap.add_argument("--first-paint", action="store_true",
                    help="print milliseconds to first map and exit (test)")
    ap.add_argument("--page", choices=PAGES, default="output")
    args = ap.parse_args(argv)

    pal = resolve_palette(args.palette)
    provider = Gtk.CssProvider()
    provider.load_from_data(css(pal).encode())
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)

    backend = spaced_sound.make_backend(fake=args.fake)
    app = SoundManager(backend, pal, preview=args.preview)

    if args.first_paint:
        t0 = time.monotonic()

        def _on_map(_w, _e):
            ms = (time.monotonic() - t0) * 1000.0
            print("FIRST_PAINT_MS=%.1f page=%s" % (ms, args.page))
            app.stack.set_visible_child_name(args.page)
            app._set_active_tab(args.page)
            GLib.idle_add(Gtk.main_quit)
            return False

        app.win.connect("map-event", _on_map)
        app.win.show_all()
        GLib.timeout_add(4000, Gtk.main_quit)  # safety
        Gtk.main()
        return 0

    if args.capture:
        return _capture(app, args.capture, args.out)

    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
