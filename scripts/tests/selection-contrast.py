#!/usr/bin/env python3
"""Issue #275: contrast of the Caja desktop selection highlight per theme.

The rule that paints a selected icon on the Caja desktop is the iconview
cell rule in the shared gtk-widgets.css (every theme @imports it):

    GtkIconView.view.cell:selected,
    GtkIconView.view.cell:selected:focus { ... }

This script resolves, per theme, the colours that rule resolves to (following
@define-color names inside that theme's gtk-3.0/*.css, including shade(),
mix() and alpha()), and prints a table of WCAG contrast ratios.
"""
import re
import sys
from pathlib import Path

THEMES_DIR = Path("overlays/usr/share/themes")
SHARED_DIR = THEMES_DIR / "Spaced-Dark" / "gtk-3.0"
RULE_SELECTOR = "GtkIconView.view.cell:selected"

NAMED = {
    "black": (0, 0, 0), "white": (255, 255, 255),
    "red": (255, 0, 0), "green": (0, 128, 0), "blue": (0, 0, 255),
    "gray": (128, 128, 128), "grey": (128, 128, 128),
    "transparent": None,
}


def clamp(v):
    return max(0.0, min(255.0, v))


def shade(color, factor):
    """GTK shade(): multiply every channel by factor."""
    return tuple(clamp(c * factor) for c in color)


def mix(c1, c2, factor):
    """GTK mix(): factor 0 -> c1, factor 1 -> c2."""
    return tuple(a * (1.0 - factor) + b * factor for a, b in zip(c1, c2))


def alpha(color, a):
    """GTK alpha(): keep the colour, attach alpha. For contrast we composite
    over the theme background, so the caller supplies the base."""
    return color + (a,)


def tokenize(expr):
    out, i = [], 0
    while i < len(expr):
        ch = expr[i]
        if ch.isspace():
            i += 1
            continue
        m = re.match(r"#[0-9a-fA-F]{3,8}", expr[i:])
        if m:
            out.append(m.group(0))
            i += m.end()
            continue
        m = re.match(r"-?[A-Za-z_][A-Za-z0-9_-]*", expr[i:])
        if m:
            out.append(m.group(0))
            i += m.end()
            continue
        m = re.match(r"-?\d*\.?\d+", expr[i:])
        if m:
            out.append(m.group(0))
            i += m.end()
            continue
        if ch in "()#%@,":
            out.append(ch)
            i += 1
            continue
        raise ValueError(f"bad char {ch!r} in {expr!r}")
    return out


class Parser:
    def __init__(self, tokens, defines, bg):
        self.toks, self.i, self.defines, self.bg = tokens, 0, defines, bg

    def peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else None

    def peek_at(self, off):
        j = self.i + off
        return self.toks[j] if j < len(self.toks) else None

    def expect(self, tok):
        got = self.toks[self.i]
        if got != tok:
            raise ValueError(f"expected {tok} got {got}")
        self.i += 1

    def parse(self):
        val = self.atom()
        while self.i < len(self.toks):
            break
        return val

    def atom(self):
        tok = self.peek()
        if tok == "(":
            self.expect("(")
            vals = [self.expr()]
            while self.peek() == ",":
                self.expect(",")
                vals.append(self.expr())
            self.expect(")")
            return vals
        if tok and tok[0] == "#":
            self.i += 1
            return (hexcolor(tok),)
        if tok == "@":
            self.expect("@")
            name = self.toks[self.i]
            self.i += 1
            if name not in self.defines:
                raise ValueError(f"undefined color @{name}")
            return (self.defines[name],)
        if re.match(r"-?\d", tok or ""):
            self.i += 1
            return (float(tok),)
        if re.match(r"[A-Za-z_]", tok or ""):
            low = tok.lower()
            if low in ("shade", "mix", "alpha") and self.peek_at(1) == "(":
                self.i += 1
                self.expect("(")
                args = [self.expr()]
                while self.peek() == ",":
                    self.expect(",")
                    args.append(self.expr())
                self.expect(")")
                if low == "shade":
                    return (shade(args[0], args[1]),)
                if low == "mix":
                    return (mix(args[0], args[1], args[2]),)
                if args[0] is None:
                    return (None,)
                return (args[0] + (args[1],),)
            if low == "rgb" and self.peek_at(1) == "(":
                self.i += 1
                self.expect("(")
                comps = [self.expr()]
                while self.peek() == ",":
                    self.expect(",")
                    comps.append(self.expr())
                self.expect(")")
                return (tuple(comps[:3]),)
            if low in NAMED:
                self.i += 1
                return (NAMED[low],)
            if tok in self.defines:
                self.i += 1
                return (self.defines[tok],)
        raise ValueError(f"cannot resolve atom at {self.i}: {tok!r}")

    def expr(self):
        vals = self.atom()
        color = vals[0]
        if color is not None and isinstance(color, tuple) and len(color) == 4:
            base = self.bg
            r, g, b, a = color
            color = (a * r + (1 - a) * base[0],
                     a * g + (1 - a) * base[1],
                     a * b + (1 - a) * base[2])
        return color


def resolve(expr, defines, bg):
    """Resolve a GTK colour expression to (r,g,b). Raises ValueError if not."""
    toks = tokenize(expr)
    p = Parser(toks, defines, bg)
    vals = p.atom()
    if p.i != len(toks):
        raise ValueError(f"trailing tokens in {expr!r}")
    return vals[0]


def hexcolor(hx):
    hx = hx.lstrip("#")
    if len(hx) == 3:
        hx = "".join(c * 2 for c in hx)
    return tuple(int(hx[i:i + 2], 16) for i in (0, 2, 4))


def parse_defines(css_text):
    defines = {}
    for m in re.finditer(r"@define-color\s+([A-Za-z0-9_-]+)\s+([^;]+);", css_text):
        name, val = m.group(1), m.group(2).strip()
        try:
            defines[name] = resolve(val, defines, (128, 128, 128))
        except ValueError:
            defines[name] = None
    return defines


def find_rule(css_texts):
    """Return the declaration block for RULE_SELECTOR."""
    joined = "\n".join(css_texts)
    for m in re.finditer(r"([^{}]*" + re.escape(RULE_SELECTOR) + r"[^{}]*)\{([^{}]*)\}", joined):
        if ":backdrop" not in m.group(1):
            return m.group(2)
    return None


def declarations(block):
    out = {}
    for m in re.finditer(r"([a-z-]+)\s*:\s*([^;]+);", block):
        out.setdefault(m.group(1), []).append(m.group(2).strip())
    return out


def luminance(color):
    def f(c):
        c /= 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = color[:3]
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(c1, c2):
    l1, l2 = luminance(c1), luminance(c2)
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


def propose_fix(sel_bg, fg):
    """Return (highlight, label, factor) keeping sel_bg's hue that passes, or None."""
    best = None
    for f in [i / 100.0 for i in range(5, 301)]:
        hi = shade(sel_bg, f)
        lab = (255, 255, 255) if contrast(hi, (255, 255, 255)) >= contrast(hi, (0, 0, 0)) else (0, 0, 0)
        if contrast(hi, (128, 128, 128)) >= 3.0 and contrast(lab, hi) >= 4.5:
            cost = abs(f - 1.0)
            if best is None or cost < best[0]:
                best = (cost, hi, lab, f)
    if best is None:
        return None
    return best[1:]


def main():
    themes = sorted(p.name for p in THEMES_DIR.iterdir() if (p / "gtk-3.0").is_dir())
    rows = []
    for theme in themes:
        tdir = THEMES_DIR / theme / "gtk-3.0"
        own_css = [p.read_text() for p in sorted(tdir.glob("*.css"))]
        shared_css = [p.read_text() for p in sorted(SHARED_DIR.glob("*.css"))] if tdir != SHARED_DIR else []
        gtk_own = (tdir / "gtk.css").read_text() if (tdir / "gtk.css").is_file() else ""
        defines = parse_defines("\n".join(own_css))
        block = find_rule([gtk_own]) or find_rule(own_css + shared_css)
        if block is None:
            rows.append((theme, "NO RULE", None, None, None, None, None, None, None))
            continue
        decls = declarations(block)
        bg = defines.get("theme_bg_color") or (128, 128, 128)
        unresolved = []
        highlight = label = None
        for prop in ("background-color", "background-image"):
            for val in decls.get(prop, []):
                if val == "none":
                    continue
                if val.startswith("linear-gradient") or val.startswith("-gtk-gradient") or "gradient" in val:
                    pat = r"(?:shade|mix|alpha)\s*\([^()]*\)|#[0-9a-fA-F]{3,6}|@[A-Za-z0-9_-]+|rgb\s*\([^()]*\)"
                    stops = re.findall(pat, val)
                    resolved_stops = []
                    for s in stops:
                        try:
                            resolved_stops.append(resolve(s.strip(), defines, bg))
                        except ValueError as e:
                            unresolved.append(f"{prop}: {s}: {e}")
                    if resolved_stops:
                        highlight = tuple(sum(c[i] for c in resolved_stops) / len(resolved_stops)
                                          for i in range(3))
                else:
                    try:
                        highlight = resolve(val, defines, bg)
                    except ValueError as e:
                        unresolved.append(f"{prop}: {e}")
        for val in decls.get("color", []):
            try:
                label = resolve(val, defines, bg)
            except ValueError as e:
                unresolved.append(f"color: {e}")
        backgrounds = {"wallpaper-unknown->#808080": (128, 128, 128),
                       "black": (0, 0, 0), "white": (255, 255, 255)}
        label_ratio = contrast(label, highlight) if label and highlight else None
        bg_ratios = {name: contrast(highlight, c) for name, c in backgrounds.items()} if highlight else {}
        rows.append((theme, highlight, label, label_ratio, bg_ratios, unresolved, block, decls, defines))

    print(f"{'theme':<18} {'highlight':<10} {'label':<8} {'label/hi':>8} {'hi/grey':>8} {'hi/black':>9} {'hi/white':>9}")
    for theme, hi, lab, lr, bgr, unresolved, *_ in rows:
        if hi is None:
            print(f"{theme:<18} unresolved: {'; '.join(unresolved) or 'no rule'}")
            continue
        hx = lambda c: "#%02x%02x%02x" % tuple(int(round(v)) for v in c[:3])
        print(f"{theme:<18} {hx(hi):<10} {hx(lab):<8} {lr:>8.2f} {bgr['wallpaper-unknown->#808080']:>8.2f} "
              f"{bgr['black']:>9.2f} {bgr['white']:>9.2f}")
        if unresolved:
            print(f"{'':<18} unresolved: {'; '.join(unresolved)}")

    print("\nFAIL (label/hi < 4.5 or hi/grey < 3.0):")
    for theme, hi, lab, lr, bgr, *_ in rows:
        if hi is None:
            continue
        if lr < 4.5 or bgr["wallpaper-unknown->#808080"] < 3.0:
            print(f"  {theme}: label/hi={lr:.2f} hi/grey={bgr['wallpaper-unknown->#808080']:.2f}")

    apply = "--apply" in sys.argv
    if apply:
        for theme, hi, lab, lr, bgr, unresolved, block, decls, defines in rows:
            if hi is None:
                continue
            if not (lr < 4.5 or bgr["wallpaper-unknown->#808080"] < 3.0):
                continue
            sel = defines.get("theme_selected_bg_color")
            fix = propose_fix(sel, defines.get("theme_selected_fg_color")) if sel else None
            if fix is None:
                continue
            nhi, nlab, f = fix
            path = THEMES_DIR / theme / "gtk-3.0" / "gtk.css"
            text = path.read_text()
            block_css = (
                "\n/* issue #275: desktop selection contrast (hue-preserving) */\n"
                "GtkIconView.view.cell:selected,\n"
                "GtkIconView.view.cell:selected:focus {\n"
                "    background-image: none;\n"
                f"    background-color: {hx(nhi)};\n"
                f"    color: {hx(nlab)};\n"
                "}\n"
            )
            path.write_text(text + block_css)
            print(f"applied override to {path}")


if __name__ == "__main__":
    sys.exit(main())
