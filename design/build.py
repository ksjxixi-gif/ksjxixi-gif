#!/usr/bin/env python3
"""Build every SVG in assets/ for the profile README (Art Deco theme).

    pip install fonttools brotli
    python3 design/build.py

Why images instead of styled HTML: GitHub strips `style` attributes and
<style> tags from READMEs, so colour, borders and typography have to live
inside SVGs. GitHub also won't let an SVG load external fonts, so each file
embeds a subset of the fonts in design/fonts/ (only the glyphs it uses),
with system fonts as a fallback.

Edit the palette or the copy below and re-run.
"""
from __future__ import annotations

import base64
import io
import math
import pathlib
from collections import defaultdict
from html import escape

from fontTools import subset
from fontTools.ttLib import TTFont

ROOT = pathlib.Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / "design" / "fonts"
OUT = ROOT / "assets"

W = 1000  # shared width so every banner and diagram lines up in the README

# ── palette ──────────────────────────────────────────────────────────────
INK = "#070B18"
PANEL = "#0C1328"
PANEL_HI = "#151E3D"
GOLD = "#D4AF37"
GOLD_LIGHT = "#F4D07A"
GOLD_PALE = "#F7E7B2"
GOLD_DEEP = "#8C6A1E"
CREAM = "#E9DCC2"
MUTED = "#A8996F"

# ── fonts: key -> (file in design/fonts, fallback stack) ─────────────────
FONTS = {
    "display": ("federo-400.woff2", "Georgia, 'Times New Roman', serif"),
    "label": ("josefin-sans-600.woff2", "'Segoe UI', Helvetica, Arial, sans-serif"),
    "light": ("josefin-sans-300.woff2", "'Segoe UI', Helvetica, Arial, sans-serif"),
    "mono": ("jetbrains-mono-500.woff2", "SFMono-Regular, Consolas, 'Liberation Mono', monospace"),
    "arabic": ("reem-kufi-arabic-600.woff2", "'Noto Kufi Arabic', 'Geeza Pro', Tahoma, sans-serif"),
}

_loaded: dict[str, TTFont] = {}


def _font(key: str) -> TTFont:
    if key not in _loaded:
        _loaded[key] = TTFont(FONT_DIR / FONTS[key][0])
    return _loaded[key]


def text_width(key: str, s: str, size: float, ls: float = 0.0) -> float:
    """Approximate rendered width (no kerning). `ls` is letter-spacing in em."""
    font = _font(key)
    cmap, hmtx = font.getBestCmap(), font["hmtx"]
    upm = font["head"].unitsPerEm
    adv = sum(hmtx[cmap[ord(c)]][0] if ord(c) in cmap else upm * 0.55 for c in s)
    return adv / upm * size + ls * size * max(len(s) - 1, 0)


def font_face(key: str, chars: set[str]) -> str:
    font = TTFont(FONT_DIR / FONTS[key][0])
    opts = subset.Options()
    opts.layout_features = ["*"]  # keeps Arabic joining forms and kerning
    opts.name_IDs = ["*"]  # keeps the copyright and licence records
    opts.name_languages = ["*"]
    sub = subset.Subsetter(opts)
    sub.populate(text="".join(sorted(chars | {" "})))
    sub.subset(font)
    font.flavor = "woff2"
    buf = io.BytesIO()
    font.save(buf)
    data = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"@font-face{{font-family:'pf-{key}';src:url(data:font/woff2;base64,{data}) format('woff2');}}"


class Svg:
    def __init__(self, w: int, h: int, title: str, desc: str = ""):
        self.w, self.h = w, h
        self.title, self.desc = title, desc
        self.defs: list[str] = []
        self.css: list[str] = []
        self.parts: list[str] = []
        self.chars: dict[str, set[str]] = defaultdict(set)
        self._ids: set[str] = set()

    def add(self, *markup: str) -> None:
        self.parts.extend(markup)

    def define(self, id_: str, markup: str) -> None:
        if id_ not in self._ids:
            self._ids.add(id_)
            self.defs.append(markup)

    def text(self, x, y, s, *, font="label", size=14.0, fill=CREAM, anchor="middle",
             ls=0.0, cls="", opacity=None, attrs="") -> None:
        cmap = _font(font).getBestCmap()
        missing = {c for c in s if c != " " and ord(c) not in cmap}
        if missing:
            raise ValueError(f"font {font!r} has no glyph for {missing!r} in {s!r}")
        self.chars[font].update(s)
        spacing = ls * size
        # Browsers add letter-spacing after the last glyph too; shift so the ink stays centred.
        if anchor == "middle":
            x += spacing / 2
        elif anchor == "end":
            x += spacing
        a = [f'x="{x:.1f}"', f'y="{y:.1f}"', f'class="f-{font}{" " + cls if cls else ""}"',
             f'font-size="{size:g}"', f'fill="{fill}"']
        if anchor != "start":
            a.append(f'text-anchor="{anchor}"')
        if ls:
            a.append(f'letter-spacing="{spacing:.2f}"')
        if opacity is not None:
            a.append(f'opacity="{opacity:g}"')
        if attrs:
            a.append(attrs)
        self.add(f"<text {' '.join(a)}>{escape(s)}</text>")

    def render(self) -> str:
        faces = "".join(font_face(k, v) for k, v in sorted(self.chars.items()))
        families = "".join(f".f-{k}{{font-family:'pf-{k}',{FONTS[k][1]}}}" for k in sorted(self.chars))
        motion = "@media (prefers-reduced-motion:reduce){*{animation:none!important}}"
        style = faces + families + "".join(self.css) + motion
        return "\n".join([
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
            f'viewBox="0 0 {self.w} {self.h}" role="img" aria-labelledby="title desc">',
            f'<title id="title">{escape(self.title)}</title>',
            f'<desc id="desc">{escape(self.desc or self.title)}</desc>',
            f"<style>{style}</style>",
            f"<defs>{''.join(self.defs)}</defs>",
            *self.parts,
            "</svg>\n",
        ])

    def save(self, rel: str) -> None:
        path = OUT / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.render(), encoding="utf-8")
        print(f"  {rel:<34} {path.stat().st_size / 1024:6.1f} KB")


# ── geometry helpers ─────────────────────────────────────────────────────
def _pts(points) -> str:
    return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in points) + " Z"


def stepped_rect(x, y, w, h, s) -> str:
    """Rectangle with double-stepped Art Deco corners."""
    r, b = x + w, y + h
    return _pts([
        (x + 2 * s, y), (r - 2 * s, y), (r - 2 * s, y + s), (r - s, y + s), (r - s, y + 2 * s), (r, y + 2 * s),
        (r, b - 2 * s), (r - s, b - 2 * s), (r - s, b - s), (r - 2 * s, b - s), (r - 2 * s, b),
        (x + 2 * s, b), (x + 2 * s, b - s), (x + s, b - s), (x + s, b - 2 * s), (x, b - 2 * s),
        (x, y + 2 * s), (x + s, y + 2 * s), (x + s, y + s), (x + 2 * s, y + s),
    ])


def plaque(x, y, w, h) -> str:
    """Elongated hexagon: a nameplate with pointed ends."""
    c = h / 2
    return _pts([(x + c, y), (x + w - c, y), (x + w, y + c), (x + w - c, y + h), (x + c, y + h), (x, y + c)])


def diamond(cx, cy, r, *, fill="none", stroke=GOLD, sw=1.0, opacity=1.0, extra="") -> str:
    return (f'<path d="{_pts([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)])}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="{sw:g}" opacity="{opacity:g}" {extra}/>')


def rays(ox, oy, a0, a1, step, r0, r1, *, color=GOLD, sw=1.0, op=(0.10, 0.05)) -> str:
    """Sunburst: lines radiating from (ox, oy) between angles a0..a1 (degrees, clockwise)."""
    groups: list[list[str]] = [[], []]
    n = int(round((a1 - a0) / step))
    for i in range(n + 1):
        a = math.radians(a0 + i * step)
        c, s = math.cos(a), math.sin(a)
        groups[i % 2].append(f"M{ox + r0 * c:.1f},{oy + r0 * s:.1f}L{ox + r1 * c:.1f},{oy + r1 * s:.1f}")
    return "".join(
        f'<path d="{"".join(g)}" stroke="{color}" stroke-width="{sw:g}" opacity="{o:g}"/>'
        for g, o in zip(groups, op) if g
    )


def arc(cx, cy, r, a0, a1) -> str:
    p0 = (cx + r * math.cos(math.radians(a0)), cy + r * math.sin(math.radians(a0)))
    p1 = (cx + r * math.cos(math.radians(a1)), cy + r * math.sin(math.radians(a1)))
    large = 1 if (a1 - a0) % 360 > 180 else 0
    return f"M{p0[0]:.1f},{p0[1]:.1f} A{r:g},{r:g} 0 {large} 1 {p1[0]:.1f},{p1[1]:.1f}"


def corner_fan(x, y, a0, r=42) -> str:
    """Quarter sunburst tucked into a frame corner: long and short rays around a small disc."""
    long_, short = [], []
    for i in range(7):
        a = math.radians(a0 + i * 15)
        rr = r if i % 2 == 0 else r * 0.6
        (long_ if i % 2 == 0 else short).append(
            f"M{x + 13 * math.cos(a):.1f},{y + 13 * math.sin(a):.1f}L{x + rr * math.cos(a):.1f},{y + rr * math.sin(a):.1f}")
    disc = f"M{x:.1f},{y:.1f}L{x + 8 * math.cos(math.radians(a0)):.1f},{y + 8 * math.sin(math.radians(a0)):.1f}" \
           f"A8,8 0 0 1 {x + 8 * math.cos(math.radians(a0 + 90)):.1f},{y + 8 * math.sin(math.radians(a0 + 90)):.1f}Z"
    return (f'<path d="{"".join(long_)}" stroke="{GOLD}" stroke-width="1" opacity="0.7"/>'
            f'<path d="{"".join(short)}" stroke="{GOLD}" stroke-width="0.8" opacity="0.45"/>'
            f'<path d="{arc(x, y, 11, a0, a0 + 90)}" fill="none" stroke="{GOLD}" stroke-width="0.8" opacity="0.6"/>'
            f'<path d="{disc}" fill="{GOLD}" opacity="0.8"/>')


def divider(svg: Svg, cx, y, half) -> None:
    """Gold rule with a centre diamond:  ◆───◇◆◇───◆"""
    svg.add(
        f'<path d="M{cx - half:.1f},{y}H{cx - 16:.1f}M{cx + 16:.1f},{y}H{cx + half:.1f}" stroke="{GOLD}" stroke-width="1"/>',
        f'<path d="M{cx - half * 0.55:.1f},{y - 5}H{cx - 22:.1f}M{cx + 22:.1f},{y - 5}H{cx + half * 0.55:.1f}'
        f'M{cx - half * 0.55:.1f},{y + 5}H{cx - 22:.1f}M{cx + 22:.1f},{y + 5}H{cx + half * 0.55:.1f}" '
        f'stroke="{GOLD}" stroke-width="0.7" opacity="0.5"/>',
        diamond(cx, y, 8, sw=1.1),
        diamond(cx, y, 3.2, fill=GOLD, stroke="none"),
        diamond(cx - half - 7, y, 3, fill=GOLD, stroke="none"),
        diamond(cx + half + 7, y, 3, fill=GOLD, stroke="none"),
    )


def gradients(svg: Svg) -> None:
    # "Chrome horizon" gold: bright top half, darker band, warm bottom.
    svg.define("gold", '<linearGradient id="gold" x1="0" y1="0" x2="0" y2="1">'
               '<stop offset="0" stop-color="#FCF1C8"/><stop offset=".46" stop-color="#F1CF6E"/>'
               '<stop offset=".54" stop-color="#C39328"/><stop offset="1" stop-color="#E8C55C"/></linearGradient>')
    svg.define("goldbar", f'<linearGradient id="goldbar" x1="0" y1="0" x2="0" y2="1">'
               f'<stop offset="0" stop-color="{GOLD_PALE}"/><stop offset=".55" stop-color="{GOLD}"/>'
               f'<stop offset="1" stop-color="{GOLD_DEEP}"/></linearGradient>')
    svg.define("goldflat", f'<linearGradient id="goldflat" x1="0" y1="0" x2="1" y2="0">'
               f'<stop offset="0" stop-color="{GOLD_DEEP}"/><stop offset=".5" stop-color="{GOLD_LIGHT}"/>'
               f'<stop offset="1" stop-color="{GOLD_DEEP}"/></linearGradient>')


def panel(svg: Svg, *, glow=(0.5, 0.0), ray_origin=None, ray_span=(180, 360), ray_len=600, bottom_fans=True) -> None:
    """Dark card with a double stepped gold frame, corner fans and an optional sunburst."""
    w, h = svg.w, svg.h
    gradients(svg)
    svg.define("glow", f'<radialGradient id="glow" cx="{glow[0]}" cy="{glow[1]}" r="0.75">'
               f'<stop offset="0" stop-color="{PANEL_HI}"/><stop offset="1" stop-color="{INK}" stop-opacity="0"/></radialGradient>')
    svg.define("inner", f'<clipPath id="inner"><path d="{stepped_rect(19, 19, w - 38, h - 38, 5)}"/></clipPath>')
    svg.add(f'<rect width="{w}" height="{h}" rx="14" fill="{INK}"/>',
            f'<rect width="{w}" height="{h}" rx="14" fill="url(#glow)"/>')
    if ray_origin:
        ox, oy = ray_origin
        svg.add(f'<g clip-path="url(#inner)">{rays(ox, oy, ray_span[0], ray_span[1], 4, 0, ray_len, op=(0.11, 0.05))}</g>')
    svg.add(f'<path d="{stepped_rect(12, 12, w - 24, h - 24, 6)}" fill="none" stroke="{GOLD}" stroke-width="1.4"/>',
            f'<path d="{stepped_rect(19, 19, w - 38, h - 38, 5)}" fill="none" stroke="{GOLD}" stroke-width="0.8" opacity="0.45"/>',
            corner_fan(29, 29, 0), corner_fan(w - 29, 29, 90))
    if bottom_fans:
        svg.add(corner_fan(w - 29, h - 29, 180), corner_fan(29, h - 29, 270))


# ── assets ───────────────────────────────────────────────────────────────
NAME = "MOHAMMAD ABUKHADIJA"
TAGLINES = [
    "I build software from the inside out.",
    "Multi-tenancy · Authorization · AI · Infrastructure",
    "Boring software is the software that keeps working.",
]


def header() -> None:
    svg = Svg(W, 320, "Mohammad Abukhadija",
              "Backend, full-stack and systems engineer and AI builder based in Jordan.")
    panel(svg, glow=(0.5, 1.0), ray_origin=(W / 2, 320), ray_span=(180, 360))
    cx = W / 2

    eyebrow = "SOFTWARE ENGINEER · JORDAN"
    ew = text_width("label", eyebrow, 12.5, 0.5) / 2 + 22
    svg.add(diamond(cx - ew, 66.5, 3, fill=GOLD, stroke="none"), diamond(cx + ew, 66.5, 3, fill=GOLD, stroke="none"))
    svg.text(cx, 71, eyebrow, size=12.5, ls=0.5, fill=MUTED)

    # Name, with a highlight that sweeps across every few seconds.
    svg.define("sheen", '<linearGradient id="sheen" gradientUnits="userSpaceOnUse" x1="-260" y1="0" x2="0" y2="0">'
               '<stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".5" stop-color="#fff" stop-opacity=".75"/>'
               '<stop offset="1" stop-color="#fff" stop-opacity="0"/>'
               '<animateTransform attributeName="gradientTransform" type="translate" values="0 0;1300 0;1300 0" '
               'keyTimes="0;.45;1" dur="7s" repeatCount="indefinite"/></linearGradient>')
    for fill in ("url(#gold)", "url(#sheen)"):
        svg.text(cx, 150, NAME, font="display", size=58, ls=0.09, fill=fill)
    divider(svg, cx, 182, 150)
    svg.text(cx, 223, "BACKEND · FULL-STACK · SYSTEMS ENGINEER · AI BUILDER", size=15, ls=0.3, fill=CREAM)

    # Rotating tagline. The first line is the resting state for renderers that don't animate.
    period = 4 * len(TAGLINES)
    svg.css.append(f".tag{{opacity:0;animation:tag {period}s infinite}}.tag0{{opacity:1}}"
                   f"@keyframes tag{{0%{{opacity:0}}4%{{opacity:1}}29%{{opacity:1}}33%{{opacity:0}}100%{{opacity:0}}}}")
    for i, line in enumerate(TAGLINES):
        delay = -((period - 4 * i) % period)
        svg.text(cx, 272, line, font="light", size=20, fill=GOLD_PALE, cls=f"tag tag{i}",
                 attrs=f'style="animation-delay:{delay}s"')
    svg.save("header.svg")


def footer() -> None:
    svg = Svg(W, 240, "Build systems. Understand everything.",
              "localhost, then staging, then production, then reality.")
    panel(svg, glow=(0.5, 0.0), ray_origin=(W / 2, 0), ray_span=(0, 180))
    cx = W / 2
    divider(svg, cx, 52, 120)
    svg.text(cx, 103, "BUILD SYSTEMS. UNDERSTAND EVERYTHING.", font="display", size=28, ls=0.12, fill="url(#gold)")

    stages = ["localhost", "staging", "production", "reality"]
    xs = [190 + i * (620 / 3) for i in range(4)]
    y = 152
    travel, period = 4.5, 6
    svg.add(f'<path d="M{xs[0]},{y}H{xs[-1]}" stroke="{GOLD}" stroke-width="1" opacity="0.7"/>',
            f'<path d="M{xs[0]},{y + 5}H{xs[-1]}" stroke="{GOLD}" stroke-width="0.6" opacity="0.35" stroke-dasharray="2 6"/>')
    svg.add(f'<g opacity="0.5">{rays(xs[-1], y, 0, 360, 22.5, 12, 30, sw=1, op=(0.9, 0.5))}</g>')
    svg.css.append(f".hit{{opacity:0;animation:hit {period}s infinite}}"
                   f"@keyframes hit{{0%{{opacity:1}}14%{{opacity:0}}100%{{opacity:0}}}}")
    for i, (x, label) in enumerate(zip(xs, stages)):
        last = i == len(stages) - 1
        svg.add(diamond(x, y, 10, fill=INK, sw=1.3),
                diamond(x, y, 4, fill=GOLD_LIGHT if last else GOLD, stroke="none"),
                diamond(x, y, 15, fill=GOLD, stroke=GOLD_PALE, sw=1,
                        extra=f'fill-opacity="0.3" class="hit" style="animation-delay:{travel / 3 * i:.2f}s"'))
        svg.text(x, y + 42, label, font="mono", size=15, fill=GOLD_LIGHT if last else CREAM)
    svg.add(f'<circle cx="{xs[0]}" cy="{y}" r="4.5" fill="{GOLD_PALE}">'
            f'<animate attributeName="cx" values="{xs[0]};{xs[-1]};{xs[-1]}" keyTimes="0;{travel / period:.3f};1" '
            f'dur="{period}s" repeatCount="indefinite"/></circle>')
    svg.save("footer.svg")


SECTIONS = [
    ("01", "WHO I AM", "01-who-i-am"),
    ("02", "WHAT I BUILD", "02-what-i-build"),
    ("03", "NIBRAS LEGALTECH", "03-nibras"),
    ("04", "ENGINEERING PHILOSOPHY", "04-philosophy"),
    ("05", "TECHNOLOGY", "05-technology"),
    ("06", "CURRENT FOCUS", "06-current-focus"),
    ("07", "ON GITHUB", "07-github"),
    ("08", "HOW I THINK", "08-how-i-think"),
]


def section(num: str, title: str, slug: str) -> None:
    # Narrower canvas than the panels so the title stays legible when phones scale it down.
    w, h = 800, 84
    svg = Svg(w, h, title.title(), f"Section {num}: {title.title()}")
    cy = h / 2
    title_size, title_ls, num_size = 23, 0.2, 13
    tw = text_width("display", title, title_size, title_ls)
    nw = text_width("mono", num, num_size)
    gap = 22
    content = nw + gap + tw
    pw = content + 110
    x0, x1 = (w - pw) / 2, (w + pw) / 2

    # side rules running out to the edges
    rule = min(150, x0 - 30)
    svg.add(f'<path d="M14,{cy}H{x0 - 14:.1f}M{x1 + 14:.1f},{cy}H{w - 14}" stroke="{GOLD}" stroke-width="1.1"/>',
            f'<path d="M{x0 - rule:.1f},{cy - 6}H{x0 - 18:.1f}M{x0 - rule * 0.7:.1f},{cy + 6}H{x0 - 18:.1f}'
            f'M{x1 + 18:.1f},{cy - 6}H{x1 + rule:.1f}M{x1 + 18:.1f},{cy + 6}H{x1 + rule * 0.7:.1f}" '
            f'stroke="{GOLD}" stroke-width="0.8" opacity="0.55"/>',
            diamond(10, cy, 3.5, fill=GOLD, stroke="none"), diamond(w - 10, cy, 3.5, fill=GOLD, stroke="none"),
            diamond(x0 - 9, cy, 3, fill=GOLD, stroke="none"), diamond(x1 + 9, cy, 3, fill=GOLD, stroke="none"))
    # the plate itself
    ph = 52
    py = cy - ph / 2
    svg.add(f'<path d="{plaque(x0, py, pw, ph)}" fill="{PANEL}" stroke="{GOLD}" stroke-width="1.4"/>',
            f'<path d="{plaque(x0 + 7, py + 5, pw - 14, ph - 10)}" fill="none" stroke="{GOLD}" stroke-width="0.7" opacity="0.45"/>')
    start = w / 2 - content / 2
    svg.text(start, cy + 4.5, num, font="mono", size=num_size, fill=MUTED, anchor="start")
    svg.add(f'<path d="M{start + nw + gap / 2:.1f},{cy - 9}V{cy + 9}" stroke="{GOLD}" stroke-width="0.8" opacity="0.6"/>')
    svg.text(start + nw + gap, cy + 8, title, font="display", size=title_size, ls=title_ls,
             fill=GOLD_LIGHT, anchor="start")
    svg.save(f"sections/{slug}.svg")


def button(label: str, slug: str) -> None:
    w, h = 230, 54
    svg = Svg(w, h, label.title())
    svg.add(f'<path d="{stepped_rect(1, 1, w - 2, h - 2, 5)}" fill="{INK}" stroke="{GOLD}" stroke-width="1.4"/>',
            f'<path d="{stepped_rect(6, 6, w - 12, h - 12, 4)}" fill="none" stroke="{GOLD}" stroke-width="0.7" opacity="0.45"/>')
    size, ls = 14, 0.32
    tw = text_width("label", label, size, ls)
    svg.add(diamond(w / 2 - tw / 2 - 20, h / 2, 4, fill=GOLD, stroke="none"),
            diamond(w / 2 + tw / 2 + 20, h / 2, 4, fill=GOLD, stroke="none"))
    svg.text(w / 2, h / 2 + 5.5, label, size=size, ls=ls, fill=GOLD_LIGHT)
    svg.save(f"buttons/{slug}.svg")


MACHINE = ["Product", "Architecture", "Frontend", "API", "Domain", "Data",
           "Identity & Authorization", "Infrastructure", "Deployment", "Observability", "Production"]


def machine() -> None:
    n = len(MACHINE)
    top, lh, gap = 98, 30, 6
    ground = top + n * (lh + gap) - gap
    svg = Svg(W, ground + 50, "The entire machine",
              "Eleven layers stacked like a tower, from Product at the top down to Production: " + ", ".join(MACHINE) + ".")
    panel(svg, glow=(0.5, 1.0), ray_origin=(W / 2, ground), ray_span=(180, 360), ray_len=560, bottom_fans=False)
    cx = W / 2

    svg.text(78, 66, "THE ENTIRE MACHINE", font="display", size=19, ls=0.12, fill=GOLD_LIGHT, anchor="start")
    svg.text(78, 88, "PRODUCT TO PRODUCTION", size=10.5, ls=0.32, fill=MUTED, anchor="start")
    svg.text(W - 78, 66, f"{n} LAYERS", font="display", size=19, ls=0.12, fill=GOLD_LIGHT, anchor="end")
    svg.text(W - 78, 88, "ONE SYSTEM", size=10.5, ls=0.32, fill=MUTED, anchor="end")

    # spire
    svg.add(f'<path d="M{cx},{top - 52}V{top - 14}" stroke="{GOLD}" stroke-width="1.2"/>',
            diamond(cx, top - 56, 5, fill=GOLD, stroke="none"),
            f'<path d="{_pts([(cx - 46, top), (cx - 46, top - 7), (cx - 28, top - 7), (cx - 28, top - 14), (cx + 28, top - 14), (cx + 28, top - 7), (cx + 46, top - 7), (cx + 46, top)])}" '
            f'fill="{PANEL}" stroke="{GOLD}" stroke-width="1"/>')

    # a request travelling down the stack
    period, step = 6.5, 0.32
    svg.css.append(f".pulse{{opacity:0;animation:pulse {period}s infinite}}"
                   f"@keyframes pulse{{0%{{opacity:0}}5%{{opacity:1}}16%{{opacity:0}}100%{{opacity:0}}}}")
    w0, w1 = 230, 800
    for i, name in enumerate(MACHINE):
        w = w0 + (w1 - w0) * i / (n - 1)
        x, y = cx - w / 2, top + i * (lh + gap)
        svg.add(f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="{lh}" fill="{PANEL}" stroke="{GOLD}" stroke-width="1"/>',
                f'<rect x="{x + 4:.1f}" y="{y + 4}" width="{w - 8:.1f}" height="{lh - 8}" fill="none" stroke="{GOLD}" stroke-width="0.5" opacity="0.3"/>',
                f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="{lh}" fill="{GOLD}" fill-opacity="0.16" '
                f'stroke="{GOLD_PALE}" stroke-width="1.6" class="pulse" style="animation-delay:{i * step:.2f}s"/>')
        svg.text(cx, y + 20, name.upper(), size=13.5, ls=0.28, fill=GOLD_PALE if i in (0, n - 1) else CREAM)
        svg.text(x - 14, y + 19.5, f"{i + 1:02d}", font="mono", size=11, fill=MUTED, anchor="end")
        svg.add(diamond(x + w + 14, y + lh / 2, 3, fill=GOLD, stroke="none", opacity=0.8))
    svg.add(f'<path d="M40,{ground + 9}H{W - 40}" stroke="{GOLD}" stroke-width="1.2"/>',
            f'<path d="M80,{ground + 15}H{W - 80}" stroke="{GOLD}" stroke-width="0.7" opacity="0.5"/>')
    svg.save("machine.svg")


NIBRAS_PILLARS = [
    ("IDENTITY", ["Authentication", "Authorization", "Granular RBAC", "Plan-aware access"]),
    ("LEGAL DOMAIN", ["Cases", "Clients", "Documents", "Tasks", "Workflows"]),
    ("INTELLIGENCE", ["OCR", "Retrieval", "Vector search", "RAG", "AI-assisted workflows"]),
    ("INFRASTRUCTURE", ["Docker", "PostgreSQL", "Nginx", "Background jobs", "Production deployment"]),
]
NIBRAS_STACK = [
    "ASP.NET CORE 8 · C# · EF CORE · REACT · TYPESCRIPT · POSTGRESQL · PGVECTOR",
    "SIGNALR · HANGFIRE · JWT · DOCKER · LINUX · NGINX",
]


def nibras() -> None:
    svg = Svg(W, 640, "Nibras LegalTech architecture",
              "A multi-tenant core holding up four pillars. "
              + " ".join(f"{name.title()}: {', '.join(items)}." for name, items in NIBRAS_PILLARS)
              + " Built on " + " ".join(NIBRAS_STACK).replace(" · ", ", ").title() + ".")
    beam_y = 206
    panel(svg, glow=(0.5, 0.3), ray_origin=(W / 2, beam_y), ray_span=(180, 360), ray_len=230, bottom_fans=False)
    cx = W / 2

    # Nibras (نبراس) means "lantern": the title sits in the light of the sunburst.
    svg.text(cx, 100, "نبراس", font="arabic", size=50, fill="url(#gold)")
    svg.text(cx, 142, "NIBRAS LEGALTECH", font="display", size=24, ls=0.3, fill=GOLD_LIGHT)
    svg.text(cx, 170, "ARABIC-FIRST LEGAL OPERATIONS · PRODUCTION SAAS", size=11.5, ls=0.3, fill=MUTED)

    # entablature
    bx0, bx1 = 66, W - 66
    svg.add(f'<path d="{_pts([(bx0 + 18, beam_y - 10), (bx1 - 18, beam_y - 10), (bx1, beam_y), (bx0, beam_y)])}" fill="{PANEL}" stroke="{GOLD}" stroke-width="1"/>',
            f'<rect x="{bx0}" y="{beam_y}" width="{bx1 - bx0}" height="42" fill="{PANEL_HI}" stroke="{GOLD}" stroke-width="1.3"/>',
            f'<rect x="{bx0 + 5}" y="{beam_y + 5}" width="{bx1 - bx0 - 10}" height="32" fill="none" stroke="{GOLD}" stroke-width="0.6" opacity="0.45"/>')
    svg.text(cx, beam_y + 28, "MULTI-TENANCY", font="display", size=19, ls=0.42, fill="url(#gold)")
    tw = text_width("display", "MULTI-TENANCY", 19, 0.42)
    for side in (-1, 1):
        svg.add(diamond(cx + side * (tw / 2 + 26), beam_y + 21, 4, fill=GOLD, stroke="none"))
    dentils = "".join(f'<rect x="{x}" y="{beam_y + 46}" width="9" height="7"/>' for x in range(bx0 + 6, bx1 - 9, 17))
    svg.add(f'<g fill="{GOLD}" opacity="0.45">{dentils}</g>')

    # columns
    cols = len(NIBRAS_PILLARS)
    span = bx1 - bx0
    cw = 194
    cgap = (span - cols * cw) / (cols - 1)
    cap_y, cap_h = 266, 38
    shaft_y, shaft_b = cap_y + cap_h, 516
    for i, (name, items) in enumerate(NIBRAS_PILLARS):
        x = bx0 + i * (cw + cgap)
        ccx = x + cw / 2
        svg.add(f'<path d="{stepped_rect(x - 6, cap_y, cw + 12, cap_h, 4)}" fill="{PANEL_HI}" stroke="{GOLD}" stroke-width="1.2"/>')
        svg.text(ccx, cap_y + 24.5, name, size=13, ls=0.22, fill=GOLD_LIGHT)
        svg.add(f'<rect x="{x}" y="{shaft_y}" width="{cw}" height="{shaft_b - shaft_y}" fill="{PANEL}" stroke="{GOLD}" stroke-width="1"/>',
                f'<path d="M{x + 9},{shaft_y + 6}V{shaft_b - 6}M{x + cw - 9},{shaft_y + 6}V{shaft_b - 6}" stroke="{GOLD}" stroke-width="0.6" opacity="0.35"/>',
                f'<rect x="{x - 6}" y="{shaft_b}" width="{cw + 12}" height="10" fill="{PANEL_HI}" stroke="{GOLD}" stroke-width="1"/>')
        pitch = 38
        first = shaft_y + (shaft_b - shaft_y) / 2 - (len(items) - 1) * pitch / 2 + 5
        for j, item in enumerate(items):
            iy = first + j * pitch
            svg.text(ccx, iy, item, size=14.5, fill=CREAM)
            if j:
                svg.add(diamond(ccx, iy - pitch / 2 - 4.5, 2.2, fill=GOLD, stroke="none", opacity=0.7))

    # stepped base carrying the stack
    steps = [(48, shaft_b + 18), (32, shaft_b + 50)]
    for (inset, sy), line in zip(steps, NIBRAS_STACK):
        svg.add(f'<rect x="{inset}" y="{sy}" width="{W - 2 * inset}" height="30" fill="{PANEL}" stroke="{GOLD}" stroke-width="1"/>')
        svg.text(cx, sy + 20, line, font="mono", size=12, ls=0.1, fill=GOLD_LIGHT)
    svg.save("nibras.svg")


PRINCIPLES = ["Understandable", "Predictable", "Testable", "Secure", "Observable", "Recoverable", "Boring"]


def philosophy() -> None:
    svg = Svg(W, 330, "Engineering philosophy",
              "A staircase of qualities, each step earning the next: " + ", ".join(PRINCIPLES) + ".")
    panel(svg, glow=(0.9, 0.0), bottom_fans=False)
    n = len(PRINCIPLES)
    base, x0, x1, gap = 300, 64, W - 76, 6
    sw = (x1 - x0 - gap * (n - 1)) / n
    svg.text(78, 70, "EACH STEP", size=11, ls=0.34, fill=MUTED, anchor="start")
    svg.text(78, 96, "earns the next.", font="display", size=22, ls=0.04, fill=GOLD_LIGHT, anchor="start")
    for i, label in enumerate(PRINCIPLES):
        last = i == n - 1
        h = 48 + i * 29
        x, y = x0 + i * (sw + gap), base - h
        sx = x + sw / 2
        svg.add(f'<rect x="{x:.1f}" y="{y}" width="{sw:.1f}" height="{h}" fill="{"url(#goldbar)" if last else PANEL}" stroke="{GOLD}" stroke-width="1.1"/>')
        if not last:
            svg.add(f'<rect x="{x + 4:.1f}" y="{y + 4}" width="{sw - 8:.1f}" height="{h - 8}" fill="none" stroke="{GOLD}" stroke-width="0.5" opacity="0.3"/>')
        svg.text(sx, y + 36, f"{i + 1:02d}", font="display", size=26, fill=INK if last else GOLD, opacity=None if last else 0.85)
        svg.text(sx, y - 14, label.upper() if last else label, size=17 if last else 15,
                 ls=0.2 if last else 0.0, fill=GOLD_PALE if last else CREAM)
    svg.add(f'<path d="M36,{base}H{W - 36}" stroke="{GOLD}" stroke-width="1.2"/>',
            f'<path d="M60,{base + 6}H{W - 60}" stroke="{GOLD}" stroke-width="0.7" opacity="0.5"/>')
    svg.save("philosophy.svg")


LOOP = ["UNDERSTAND", "MAP", "DESIGN", "BUILD", "BREAK", "FIX", "SHIP", "OBSERVE"]


def loop() -> None:
    svg = Svg(W, 540, "My usual loop",
              "A clockwise cycle: " + ", ".join(s.title() for s in LOOP)
              + ", then repeat until the system stops surprising you.")
    panel(svg, glow=(0.5, 0.5))
    cx, cy, R = W / 2, 270, 200
    n = len(LOOP)
    period = n  # one second per stage

    svg.text(78, 66, "MY USUAL LOOP", font="display", size=19, ls=0.12, fill=GOLD_LIGHT, anchor="start")
    svg.text(78, 88, f"{n} STAGES · NO LAST ONE", size=10.5, ls=0.32, fill=MUTED, anchor="start")

    # dial
    ticks = "".join(
        f"M{cx + (R + 9) * math.cos(math.radians(a)):.1f},{cy + (R + 9) * math.sin(math.radians(a)):.1f}"
        f"L{cx + (R + (17 if a % 45 == 0 else 13)) * math.cos(math.radians(a)):.1f},"
        f"{cy + (R + (17 if a % 45 == 0 else 13)) * math.sin(math.radians(a)):.1f}"
        for a in range(0, 360, 5))
    svg.add(f'<path d="{ticks}" stroke="{GOLD}" stroke-width="0.8" opacity="0.4"/>',
            f'<circle cx="{cx}" cy="{cy}" r="{R}" fill="none" stroke="{GOLD}" stroke-width="1.3"/>',
            f'<circle cx="{cx}" cy="{cy}" r="{R - 9}" fill="none" stroke="{GOLD}" stroke-width="0.6" opacity="0.4"/>',
            rays(cx, cy, 0, 360, 7.5, 108, 168, op=(0.22, 0.1)),
            f'<circle cx="{cx}" cy="{cy}" r="104" fill="{PANEL}" stroke="{GOLD}" stroke-width="1.2"/>',
            f'<circle cx="{cx}" cy="{cy}" r="97" fill="none" stroke="{GOLD}" stroke-width="0.6" opacity="0.45"/>')
    for k, line in enumerate(["REPEAT UNTIL", "THE SYSTEM STOPS", "SURPRISING YOU"]):
        svg.text(cx, cy - 14 + k * 24, line, size=13, ls=0.18, fill=GOLD_PALE if k == 1 else CREAM)
    svg.add(diamond(cx, cy - 50, 3.5, fill=GOLD, stroke="none"), diamond(cx, cy + 56, 3.5, fill=GOLD, stroke="none"))

    # direction chevrons between stations
    for i in range(n):
        a = -90 + 360 / n * (i + 0.5)
        px, py = cx + R * math.cos(math.radians(a)), cy + R * math.sin(math.radians(a))
        svg.add(f'<path d="M-4,-6L3,0L-4,6" fill="none" stroke="{GOLD_LIGHT}" stroke-width="1.6" '
                f'transform="translate({px:.1f},{py:.1f}) rotate({a + 90:.1f})"/>')

    # comet riding the ring (drawn under the stations so it ducks beneath them)
    trail = "".join(
        f'<circle cx="{cx + R * math.cos(math.radians(-90 - d)):.1f}" cy="{cy + R * math.sin(math.radians(-90 - d)):.1f}" '
        f'r="{r}" fill="{GOLD_PALE}" opacity="{o}"/>'
        for d, r, o in ((0, 11, 0.18), (0, 5.5, 1), (3.2, 4, 0.55), (6.4, 3, 0.3), (9.6, 2.2, 0.15)))
    svg.add(f'<g>{trail}<animateTransform attributeName="transform" type="rotate" from="0 {cx} {cy}" '
            f'to="360 {cx} {cy}" dur="{period}s" repeatCount="indefinite"/></g>')

    svg.css.append(f".lit{{opacity:0;animation:lit {period}s infinite}}"
                   f"@keyframes lit{{0%{{opacity:0}}3%{{opacity:1}}16%{{opacity:0}}100%{{opacity:0}}}}")
    pw, ph = 152, 42
    for i, label in enumerate(LOOP):
        a = math.radians(-90 + 360 / n * i)
        px, py = cx + R * math.cos(a), cy + R * math.sin(a)
        shape = plaque(px - pw / 2, py - ph / 2, pw, ph)
        svg.add(f'<path d="{shape}" fill="{PANEL}" stroke="{GOLD}" stroke-width="1.3"/>',
                f'<path d="{plaque(px - pw / 2 + 6, py - ph / 2 + 4, pw - 12, ph - 8)}" fill="none" stroke="{GOLD}" stroke-width="0.6" opacity="0.4"/>',
                f'<path d="{shape}" fill="{GOLD}" fill-opacity="0.2" stroke="{GOLD_PALE}" stroke-width="2" '
                f'class="lit" style="animation-delay:{i - 0.15:.2f}s"/>')
        svg.text(px, py + 5, label, size=13.5, ls=0.26, fill=GOLD_LIGHT)
    svg.save("loop.svg")


def main() -> None:
    print("Building assets/")
    header()
    footer()
    for s in SECTIONS:
        section(*s)
    button("PORTFOLIO", "portfolio")
    button("EMAIL", "email")
    machine()
    nibras()
    philosophy()
    loop()


if __name__ == "__main__":
    main()
