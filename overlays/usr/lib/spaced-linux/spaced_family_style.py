#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""One set of colour tokens for the Spaced app family (FAMILY-LOOK.md).

The GPU Manager and the Sound Manager both import this so the two stay
identical in every theme, exactly like Spaced Monitor (spaced_monitor/theme.py).
The dark tokens are navy, never grey: a Spaced dark card on ANY dark desktop
theme (Spaced-Win11-Dark's #172742, Spaced-Dark's #383838, Spaced-Linux-Dark's
#2f2f2f ...) paints the family navy, because a grey card is wrong in every dark
theme. Light tokens are the same layout in light fill with dark text and the
same accent/pill colours. ``accent_ink`` is the darker accent used only behind
white text (active tab, primary button) so white text clears WCAG 4.5; the
bright accent stays for sliders, borders and the thin underline.

Nothing here reads a GTK theme or the network; both apps resolve dark/light
from the desktop and use these fixed tokens.
"""
from __future__ import annotations

from dataclasses import dataclass


def _hex(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def css_colour(c: tuple) -> str:
    """(r, g, b) floats in 0-1 -> '#rrggbb'."""
    return "#{:02x}{:02x}{:02x}".format(*(int(round(min(1.0, max(0.0, x)) * 255))
                                         for x in c))


def rgba(c: tuple, a: float) -> str:
    """(r, g, b) floats + alpha -> 'rgba(r,g,b,a)' for GTK CSS."""
    r, g, b = (int(round(min(1.0, max(0.0, x)) * 255)) for x in c)
    return "rgba({},{},{},{})".format(r, g, b, a)


def mix(base: tuple, target: tuple, amount: float) -> tuple:
    """Linear blend of ``base`` towards ``target`` by ``amount`` (0-1)."""
    return tuple(b + (t - b) * amount for b, t in zip(base, target))


def lightness(c: tuple) -> float:
    """Perceptual lightness (0-1); < 0.5 means a dark colour."""
    r, g, b = c
    return 0.299 * r + 0.587 * g + 0.114 * b


# --------------------------------------------------------------------- WCAG
def _lin(x: float) -> float:
    return x / 12.92 if x <= 0.0392 else ((x + 0.055) / 1.055) ** 2.4


def relative_luminance(c: tuple) -> float:
    """WCAG relative luminance from sRGB floats."""
    r, g, b = c
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def contrast_ratio(a: tuple, b: tuple) -> float:
    """WCAG contrast ratio (1-21) between two colours."""
    la, lb = relative_luminance(a), relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


# --------------------------------------------------------------------- tokens
@dataclass(frozen=True)
class Palette:
    """The family tokens, defined once. Names Spaced Monitor already uses."""
    window: tuple
    band: tuple
    card: tuple
    border: tuple
    text: tuple
    muted: tuple
    accent: tuple
    accent_ink: tuple
    ok: tuple
    warn: tuple
    ai: tuple
    off: tuple
    track: tuple
    level_start: tuple
    level_mid: tuple
    level_peak: tuple

    @property
    def bg(self) -> tuple:
        """Sound Manager's name for the page/window background."""
        return self.window

    @property
    def meter_track(self) -> tuple:
        """Sound Manager's name for the idle meter segment colour."""
        return self.track


# Navy DARK. window/band/card/border follow the Spaced navy family (Spaced
# Monitor's DARK), so a dark card is navy on every dark theme - not grey.
DARK = Palette(
    window=_hex("#0b1220"), band=_hex("#0e1526"), card=_hex("#111a2e"),
    border=_hex("#1e2a44"), text=_hex("#e6ecf5"), muted=_hex("#8a96ab"),
    accent=_hex("#1e9be0"), accent_ink=_hex("#1668a8"),
    ok=_hex("#22c55e"), warn=_hex("#f59e0b"), ai=_hex("#8b5cf6"),
    off=_hex("#6b7488"), track=_hex("#1e2a44"),
    level_start=_hex("#22c55e"), level_mid=_hex("#f59e0b"),
    level_peak=_hex("#ef4444"),
)
LIGHT = Palette(
    window=_hex("#eef2f8"), band=_hex("#f7f9fc"), card=_hex("#ffffff"),
    border=_hex("#dfe5ee"), text=_hex("#1f2937"), muted=_hex("#6b7280"),
    accent=_hex("#1e9be0"), accent_ink=_hex("#1668a8"),
    ok=_hex("#16a34a"), warn=_hex("#d97706"), ai=_hex("#7c3aed"),
    off=_hex("#64748b"), track=_hex("#e2e6ee"),
    level_start=_hex("#16a34a"), level_mid=_hex("#d97706"),
    level_peak=_hex("#dc2626"),
)


def palette_for(dark: bool) -> Palette:
    """The fixed family palette for a dark or light desktop."""
    return DARK if dark else LIGHT


# PILL/TEXT CONTRAST ----------------------------------------------------------
# A status pill is a tinted translucent fill over the page background, a
# coloured 1px border, and the theme's text colour (FAMILY-LOOK item 5). The
# active tab / primary button is an ``accent_ink`` fill with white text.
# ``fill_and_text`` returns the concrete colours the CSS will paint, so the CSS
# and its contrast test can never drift apart.
PILL_KINDS = ("ok", "warn", "ai", "off", "games")


def _status_colour(pal: Palette, kind: str) -> tuple:
    return {"ok": pal.ok, "warn": pal.warn, "ai": pal.ai, "off": pal.off,
            "games": pal.accent}[kind]


def pill_fill_and_text(pal: Palette, kind: str) -> tuple:
    """(fill, text) as 0-1 floats for a status pill of ``kind``."""
    fill = mix(pal.card, _status_colour(pal, kind), 0.18)
    return fill, pal.text


def active_tab_fill_and_text(pal: Palette) -> tuple:
    """(fill, text) for the active tab pill (accent_ink + white)."""
    return pal.accent_ink, (1.0, 1.0, 1.0)


def contrast_pairs(pal: Palette) -> list:
    """Every (name, text, fill) the CSS paints for pills/tabs, for the test."""
    pairs = [("tab-active",) + active_tab_fill_and_text(pal)]
    for kind in PILL_KINDS:
        fill, text = pill_fill_and_text(pal, kind)
        pairs.append(("pill-" + kind, text, fill))
    return pairs
