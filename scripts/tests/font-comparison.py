#!/usr/bin/env python3
# Render one 900x420 card per installed font family and measure text width + x-height (issue #286).
# Cairo (cairo-gobject) is not available on this machine, so cards are rendered with Pillow and
# measured with Pillow's textbbox; the numbers therefore match the pictures exactly.
import sys
from PIL import Image, ImageDraw, ImageFont

SENTENCE = "The quick brown fox jumps over the lazy dog near a big barn!"  # 60 chars
MENU = "File  Edit  View  Bookmarks  Help"
LOOKALIKE = "Il1 O0 rn m"
TITLE = "Spaced Linux - File Manager"
PARA = ("A window title and menu labels at the default size, then the same paragraph "
        "one point larger, so the reader can compare how much text fits on a line.")

W, H = 900, 420
DPI = 96.0


def pt2px(pt):
    return int(round(pt * DPI / 72.0))


def resolve(reg, bold):
    import subprocess
    def match(spec):
        out = subprocess.run(["fc-match", "-f", "%{file}", spec],
                             capture_output=True, text=True)
        return out.stdout.strip()
    return match(reg), match(bold)


def measure(font_file, size_px):
    f = ImageFont.truetype(font_file, size_px)
    x0, y0, x1, y1 = f.getbbox(SENTENCE)
    width = x1 - x0
    ax0, ay0, ax1, ay1 = f.getbbox("x")
    return width, (ay1 - ay0)


def wrap(draw, font, text, x, y, maxw, lh):
    words = text.split()
    line = ""
    for word in words:
        trial = (line + " " + word).strip()
        if draw.textbbox((0, 0), trial, font=font)[2] > maxw:
            if line:
                draw.text((x, y), line, font=font)
                y += lh
                line = word
            else:
                draw.text((x, y), word, font=font)
                y += lh
                line = ""
        else:
            line = trial
    if line:
        draw.text((x, y), line, font=font)
        y += lh
    return y


def card(reg_file, bold_file):
    img = Image.new("RGB", (W, H), (240, 240, 240))
    img.paste((32, 32, 32), (0, H // 2, W, H))
    d = ImageDraw.Draw(img)
    s10 = pt2px(10)
    s11 = pt2px(11)
    for half, bg, fg in (("light", (240, 240, 240), (20, 20, 20)),
                        ("dark", (32, 32, 32), (235, 235, 235))):
        top = 0 if half == "light" else H // 2
        d.rectangle([0, top, W, top + H // 2], fill=bg)
        y = top + 12
        d.text((8, y), FAMILY, font=ImageFont.truetype(bold_file, pt2px(14)), fill=fg)
        y += pt2px(14) + 8
        d.text((8, y), TITLE, font=ImageFont.truetype(bold_file, s10), fill=fg)
        y += s10 + 8
        d.text((8, y), MENU, font=ImageFont.truetype(reg_file, s10), fill=fg)
        y += s10 + 10
        y = wrap(d, ImageFont.truetype(reg_file, s10), PARA, 8, y, W - 16, s10 + 4)
        y += 6
        y = wrap(d, ImageFont.truetype(reg_file, s11), PARA, 8, y, W - 16, s11 + 4)
        y += 8
        d.text((8, y), LOOKALIKE, font=ImageFont.truetype(reg_file, s10), fill=fg)
    return img


def main(outdir, families):
    global FAMILY
    rows = []
    cards = []
    for fam in families:
        FAMILY = fam
        reg, bold = resolve(fam, f"{fam}:bold")
        width, xh = measure(reg, pt2px(10))
        img = card(reg, bold)
        path = f"{outdir}/{'_'.join(fam.split())}.png"
        img.save(path)
        cards.append((path, img))
        rows.append((fam, width, xh, reg))
    rows.sort(key=lambda r: r[1])
    cols = len(cards)
    sheet = Image.new("RGB", (cols * W, 2 * H), (255, 255, 255))
    for i, (_, img) in enumerate(cards):
        sheet.paste(img, ((i % 3) * W, (i // 3) * H))
    sheet.save(f"{outdir}/contact-sheet.png")
    with open(f"{outdir}/README.md", "w") as fh:
        fh.write("# Default font comparison (issue #286)\n\n")
        fh.write("Width = pixels of the 60-character sentence at 10 pt (narrower fits more text). "
                 "x-height = pixels of the lowercase 'x' at 10 pt.\n\n")
        fh.write("| Family | Width (px) | x-height (px) | File |\n")
        fh.write("|---|---|---|---|\n")
        for fam, width, xh, reg in rows:
            fh.write(f"| {fam} | {width} | {xh} | {reg} |\n")
        fh.write("\n![contact sheet](contact-sheet.png)\n")
    for fam, width, xh, reg in rows:
        print(f"{fam}\twidth={width}px\tx-height={xh}px")


if __name__ == "__main__":
    outdir = sys.argv[1]
    fams = sys.argv[2:]
    main(outdir, fams)
