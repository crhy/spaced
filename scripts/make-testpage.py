#!/usr/bin/env python3
"""Generate the Spaced Linux CUPS printer test page.

A real test page, not a text-only stub: a colour grid of the seven ink swatches
(cyan, magenta, yellow, black, red, green, blue), each drawn half solid and
half 50% dot-screened, a 12-step grey wheel, a 1 cm ruler along two edges and a
thin 10 mm margin frame for alignment/clipping checks. Rendered with pycairo
(cairo PDFSurface) at A4. The PDF Title is "Spaced Linux Test Page" and the
page carries no Debian branding.

Run:  python3 scripts/make-testpage.py
Output: overlays/usr/share/cups/data/default-testpage.pdf
"""
import math
import os

import cairo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGO = os.path.join(ROOT, "overlays", "usr", "share", "pixmaps", "spaced-logo.png")
OUT = os.path.join(ROOT, "overlays", "usr", "share", "cups", "data",
                   "default-testpage.pdf")

# A4 in points (as used by the stock page this file overrides).
PAGE_W, PAGE_H = 595.276, 841.89
MM = 72.0 / 25.4           # one millimetre in points
MM10 = 10.0 * MM           # 10 mm margin frame
CM = 10.0 * MM             # 1 cm ruler step

# Ink swatches: (name, rgb).
SWATCHES = [
    ("Cyan",    (0.0, 1.0, 1.0)),
    ("Magenta", (1.0, 0.0, 1.0)),
    ("Yellow",  (1.0, 1.0, 0.0)),
    ("Black",   (0.0, 0.0, 0.0)),
    ("Red",     (1.0, 0.0, 0.0)),
    ("Green",   (0.0, 1.0, 0.0)),
    ("Blue",    (0.0, 0.0, 1.0)),
]


def text(ctx, x, y, s, size, rgb=(0, 0, 0), align="left"):
    ctx.select_font_face("sans")
    ctx.set_font_size(size)
    ctx.set_source_rgb(*rgb)
    ext = ctx.text_extents(s)
    ox = x
    if align == "center":
        ox = x - ext.width / 2.0
    elif align == "right":
        ox = x - ext.width
    ctx.move_to(ox, y)
    ctx.show_text(s)


def half_screen_circle(ctx, cx, cy, r, rgb):
    """Left semicircle solid, right semicircle 50% dot-screened, thin outline."""
    ctx.save()
    ctx.new_path()
    ctx.arc(cx, cy, r, 0, 2 * math.pi)
    ctx.clip()
    # solid left half
    ctx.set_source_rgb(*rgb)
    ctx.rectangle(cx - r, cy - r, r, 2 * r)
    ctx.fill()
    # screened right half: white ground then ~50% area dots
    ctx.set_source_rgb(1, 1, 1)
    ctx.rectangle(cx, cy - r, r, 2 * r)
    ctx.fill()
    ctx.set_source_rgb(*rgb)
    step = 4.0
    dot = step * 0.399          # area fraction ~ pi*dot^2/step^2 ~= 0.5
    gx = cx
    while gx <= cx + r + step:
        gy = cy - r
        while gy <= cy + r + step:
            ctx.new_path()
            ctx.arc(gx, gy, dot, 0, 2 * math.pi)
            ctx.fill()
            gy += step
        gx += step
    ctx.restore()
    ctx.set_source_rgb(0, 0, 0)
    ctx.set_line_width(0.6)
    ctx.new_path()
    ctx.arc(cx, cy, r, 0, 2 * math.pi)
    ctx.stroke()


def grey_wheel(ctx, cx, cy, r, steps=12):
    """Circle split into `steps` wedges stepping from black to white."""
    for i in range(steps):
        a0 = math.radians(i * 360.0 / steps - 90)
        a1 = math.radians((i + 1) * 360.0 / steps - 90)
        g = i / (steps - 1)
        ctx.set_source_rgb(g, g, g)
        ctx.new_path()
        ctx.move_to(cx, cy)
        ctx.arc(cx, cy, r, a0, a1)
        ctx.close_path()
        ctx.fill()
    ctx.set_source_rgb(0, 0, 0)
    ctx.set_line_width(0.6)
    ctx.new_path()
    ctx.arc(cx, cy, r, 0, 2 * math.pi)
    ctx.stroke()


def ruler(ctx, along):
    """1 cm tick ruler with mm minors and cm numbers along one edge."""
    ctx.set_source_rgb(0, 0, 0)
    ctx.set_line_width(0.4)
    if along == "top":
        y0 = MM10
        ctx.move_to(MM10, y0)
        ctx.line_to(PAGE_W - MM10, y0)
        ctx.stroke()
        p = MM10
        while p <= PAGE_W - MM10:
            cm = round((p - MM10) / CM)
            if abs(p - (MM10 + cm * CM)) < 0.01:
                tick = 6.0
                ctx.move_to(p, y0)
                ctx.line_to(p, y0 + tick)
                ctx.stroke()
                text(ctx, p, y0 + tick + 8, str(cm), 6, align="center")
            else:
                ctx.move_to(p, y0)
                ctx.line_to(p, y0 + 3.0)
                ctx.stroke()
            p += MM
    else:  # left
        x0 = MM10
        ctx.move_to(x0, MM10)
        ctx.line_to(x0, PAGE_H - MM10)
        ctx.stroke()
        p = MM10
        while p <= PAGE_H - MM10:
            cm = round((p - MM10) / CM)
            if abs(p - (MM10 + cm * CM)) < 0.01:
                tick = 6.0
                ctx.move_to(x0, p)
                ctx.line_to(x0 + tick, p)
                ctx.stroke()
                ctx.save()
                ctx.translate(x0 + tick + 8, p)
                ctx.rotate(-math.pi / 2)
                text(ctx, 0, 0, str(cm), 6, align="center")
                ctx.restore()
            else:
                ctx.move_to(x0, p)
                ctx.line_to(x0 + 3.0, p)
                ctx.stroke()
            p += MM


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    surface = cairo.PDFSurface(OUT, PAGE_W, PAGE_H)
    try:
        surface.set_metadata(cairo.PDFMetadata.TITLE, "Spaced Linux Test Page")
        surface.set_metadata(cairo.PDFMetadata.CREATOR, "Spaced Linux")
        surface.set_metadata(cairo.PDFMetadata.CREATE_DATE, "D:20261126000000Z")
    except Exception:
        pass
    ctx = cairo.Context(surface)
    ctx.set_antialias(cairo.ANTIALIAS_DEFAULT)

    # white background
    ctx.set_source_rgb(1, 1, 1)
    ctx.paint()

    # thin 10 mm margin frame (alignment/clipping check)
    ctx.set_source_rgb(0, 0, 0)
    ctx.set_line_width(0.5)
    ctx.rectangle(MM10, MM10, PAGE_W - 2 * MM10, PAGE_H - 2 * MM10)
    ctx.stroke()

    # 1 cm rulers along the top and left edges
    ruler(ctx, "top")
    ruler(ctx, "left")

    # header: logo + title
    logo = None
    if os.path.exists(LOGO):
        try:
            logo = cairo.ImageSurface.create_from_png(LOGO)
        except Exception:
            logo = None
    if logo is not None:
        scale = 46.0 / logo.get_height()
        ctx.save()
        ctx.translate(MM10 + 8, MM10 + 12)
        ctx.scale(scale, scale)
        ctx.set_source_surface(logo, 0, 0)
        ctx.paint()
        ctx.restore()
        logo_w = logo.get_width() * scale
    else:
        logo_w = 0
    text(ctx, MM10 + 8 + logo_w + 10, MM10 + 44,
         "Spaced Linux - printer test page", 17)
    text(ctx, MM10 + 8 + logo_w + 10, MM10 + 58,
         "Colour, grey-scale and alignment check", 10, (0.35, 0.35, 0.35))

    # seven ink swatches: 4 on the top row, 3 on the second row
    r = 30.0
    row1 = SWATCHES[:4]
    row2 = SWATCHES[4:]
    y1, y2 = MM10 + 150.0, MM10 + 250.0
    x = 95.0
    for name, rgb in row1:
        half_screen_circle(ctx, x, y1, r, rgb)
        text(ctx, x, y1 + r + 13, name, 8, align="center")
        x += 112.0
    x = 151.0
    for name, rgb in row2:
        half_screen_circle(ctx, x, y2, r, rgb)
        text(ctx, x, y2 + r + 13, name, 8, align="center")
        x += 112.0

    # 12-step grey wheel to the right of the swatch rows
    grey_wheel(ctx, 470.0, y1 + 50.0, 46.0, 12)
    text(ctx, 470.0, y1 + 50.0 + 46.0 + 13, "12-step grey wheel", 8,
         align="center")

    # footer line
    text(ctx, PAGE_W / 2.0, PAGE_H - MM10 - 26.0,
         "If you can read this page, your printer works.", 12,
         align="center")

    surface.show_page()
    surface.flush()
    surface.finish()


if __name__ == "__main__":
    main()
