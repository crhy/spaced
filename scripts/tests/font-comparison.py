#!/usr/bin/env python3
# Render one card per font family and measure text width, x-height and line height (issue #286).
# Text is laid out with Pango and drawn with Cairo, the same stack GTK uses on the desktop, at
# the size the desktop really shows: "Sans 10" times the shipped text-scaling-factor of 1.2.
import sys

import cairo
import gi

gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Pango, PangoCairo  # noqa: E402

SENTENCE = "The quick brown fox jumps over the lazy dog near a big barn!"  # 60 chars
TITLE = "Spaced Linux - File Manager"
MENU = "File   Edit   View   Go   Bookmarks   Help"
PARA = ("Spaced Linux is a free desktop that looks the way you are used to, comes with a voice "
        "assistant that runs on your own hardware, and never asks you to sign in.")
LOOKALIKE = "Il1| O0o rn m cl d 5S 8B 2Z  0123456789  .,;:!?  ()[]{}"

POINT_SIZE = 10
SCALE = 1.2  # text-scaling-factor in 90_spaced-linux.gschema.override
DPI = 96.0
W, PAD, COLS = 900, 14, 3
BASELINE = "DejaVu Sans"  # what "Sans" resolves to on a stock install
HALVES = (((0.94, 0.94, 0.94), (0.08, 0.08, 0.08)), ((0.13, 0.13, 0.13), (0.92, 0.92, 0.92)))


def make_layout(ctx, family, text, bold=False, size=POINT_SIZE, width=None):
    layout = PangoCairo.create_layout(ctx)
    PangoCairo.context_set_resolution(layout.get_context(), DPI * SCALE)
    desc = Pango.FontDescription()
    desc.set_family(family)
    desc.set_size(int(size * Pango.SCALE))
    desc.set_weight(Pango.Weight.BOLD if bold else Pango.Weight.NORMAL)
    layout.set_font_description(desc)
    if width:
        layout.set_width(width * Pango.SCALE)
        layout.set_wrap(Pango.WrapMode.WORD)
    layout.set_text(text, -1)
    return layout


def resolved_family(ctx, family):
    layout = make_layout(ctx, family, "x")
    font = layout.get_context().load_font(layout.get_font_description())
    return font.describe().get_family()


def rows(family):
    return ((family, True, 14), (TITLE, True, POINT_SIZE), (MENU, False, POINT_SIZE),
            (PARA, False, POINT_SIZE), (LOOKALIKE, False, POINT_SIZE))


def draw_half(ctx, family, top, bg, fg, paint=True):
    y = top + PAD
    height = 0
    for text, bold, size in rows(family):
        layout = make_layout(ctx, family, text, bold, size, W - 2 * PAD)
        if paint:
            ctx.set_source_rgb(*fg)
            ctx.move_to(PAD, y)
            PangoCairo.show_layout(ctx, layout)
        y += layout.get_pixel_size()[1] + 8
    height = y - top + PAD - 8
    return height


def card(family, half_height):
    surface = cairo.ImageSurface(cairo.FORMAT_RGB24, W, 2 * half_height)
    ctx = cairo.Context(surface)
    for i, (bg, fg) in enumerate(HALVES):
        ctx.set_source_rgb(*bg)
        ctx.rectangle(0, i * half_height, W, half_height)
        ctx.fill()
        draw_half(ctx, family, i * half_height, bg, fg)
    return surface


def measure(ctx, family):
    width = make_layout(ctx, family, SENTENCE).get_pixel_size()[0]
    ink, _ = make_layout(ctx, family, "x").get_pixel_extents()
    line = make_layout(ctx, family, "x").get_pixel_size()[1]
    return width, ink.height, line


def main(outdir, families):
    probe = cairo.Context(cairo.ImageSurface(cairo.FORMAT_RGB24, 8, 8))
    present = [f for f in families if resolved_family(probe, f) == f]
    missing = [f for f in families if f not in present]
    half = max(draw_half(probe, f, 0, None, None, paint=False) for f in present)

    results = []
    for family in present:
        surface = card(family, half)
        surface.write_to_png(f"{outdir}/{family.replace(' ', '_')}.png")
        results.append((family, *measure(probe, family), surface))
    results.sort(key=lambda r: r[1])

    # Contact sheet in the same narrow-to-wide order as the table.
    grid_rows = -(-len(results) // COLS)
    sheet = cairo.ImageSurface(cairo.FORMAT_RGB24, COLS * W, grid_rows * 2 * half)
    ctx = cairo.Context(sheet)
    ctx.set_source_rgb(1, 1, 1)
    ctx.paint()
    for i, result in enumerate(results):
        ctx.set_source_surface(result[4], (i % COLS) * W, (i // COLS) * 2 * half)
        ctx.paint()
    sheet.write_to_png(f"{outdir}/contact-sheet.png")

    base = next((r[1] for r in results if r[0] == BASELINE), None)
    with open(f"{outdir}/README.md", "w") as fh:
        fh.write("# Default font comparison (issue #286)\n\n")
        fh.write(f"Rendered with Pango and Cairo at {POINT_SIZE} pt with the shipped text scaling "
                 f"of {SCALE}, which is what a stock desktop shows. Width is the pixel width of a "
                 "60-character sentence, so a smaller number fits more text on a line. x-height is "
                 "the pixel height of a lowercase x, and line height is the pixel height of one "
                 f"line. The last column compares the width with {BASELINE}, the current default.\n\n")
        fh.write(f"| Family | Width (px) | x-height (px) | Line height (px) | Width vs {BASELINE} |\n")
        fh.write("|---|---|---|---|---|\n")
        for family, width, xh, line, _ in results:
            rel = f"{(width / base - 1) * 100:+.0f}%" if base else "n/a"
            fh.write(f"| [{family}]({family.replace(' ', '_')}.png) | {width} | {xh} | {line} | {rel} |\n")
        if missing:
            fh.write(f"\nNot available when this was generated, so not compared: {', '.join(missing)}.\n")
        fh.write("\n![contact sheet](contact-sheet.png)\n")

    for family, width, xh, line, _ in results:
        print(f"{family}\twidth={width}px\tx-height={xh}px\tline={line}px")
    if missing:
        print("not available (not compared): " + ", ".join(missing))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
