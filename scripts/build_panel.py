#!/usr/bin/env python3
"""Render the profile panel.

The wordmark, market ticker, ASCII portrait and info block are painted into one
image. Output format is chosen by the extension:

    python3 scripts/build_panel.py assets/panel.svg   # animated SVG (SMIL)
    python3 scripts/build_panel.py assets/panel.gif    # animated GIF (frames)

The SVG animates with SMIL — crisp, tiny, but only on desktop browsers. The GIF
bakes the same motion into frames so it animates everywhere, including the
GitHub mobile app. Building the GIF needs `rsvg-convert` and `magick` on PATH.

Source text lives next to the rendered output:
    assets/wordmark.txt       figlet wordmark, painted onto a fixed glyph grid
    assets/alien-frames.txt   portrait frames, separated by `===FRAME===`
"""
import html
import math
import os
import random
import subprocess
import sys
import tempfile

OUT = sys.argv[1] if len(sys.argv) > 1 else "assets/panel.svg"

# GIF loop length, chosen so every motion repeats seamlessly within it:
# portrait (1.6s) x3, candle bob (2.4s) x2, scroll one period x1.
LOOP = 4.8
FPS = 12

# Palette ---------------------------------------------------------------------
BG, BORDER   = "#0B0B0C", "#1C1D22"
HEADER, DIM  = "#E8EAED", "#5A6069"
LABEL, VALUE = "#3B92F0", "#C9CDD3"
RULE, LEADER = "#272A30", "#34373E"
UP, DOWN     = "#26A69A", "#EF5350"            # candle up / down
GLOW         = ("#2E9BEE", 0.18)               # colour, opacity
GRADIENT     = [("0%", "#8FD6FF"), ("50%", "#33A0F0"), ("100%", "#2070DD")]
MONO = "ui-monospace, SFMono-Regular, Menlo, 'DejaVu Sans Mono', Consolas, monospace"

# Info block ------------------------------------------------------------------
INFO = [
    ("head", "who is aaditya?"),
    ("row",  "age",       "23"),
    ("row",  "based",     "bay area / nyc"),
    ("row",  "building",  "blockhouse"),
    ("row",  "interests", "defi · mev · quantitative trading · agents"),
    ("gap",),
    ("sect", "contact"),
    ("row",  "site",      "aadityatrades.com"),
    ("row",  "x",         "@aaditya_trades"),
    ("row",  "email",     "aaditya@blockhouse.capital"),
]

# Geometry --------------------------------------------------------------------
PAD        = 34
PORTRAIT_H = 344        # ASCII portrait height
INFO_W     = 470
INFO_FS    = 13
INFO_CW    = 7.80       # monospace advance at INFO_FS
INFO_LH    = 22.0
TICKER_H   = 30


def read_lines(path):
    """Read a text figure, trimming blank leading/trailing rows."""
    lines = open(path, encoding="utf-8").read().split("\n")
    while lines and not lines[0].strip():  lines.pop(0)
    while lines and not lines[-1].strip(): lines.pop()
    return lines


def read_frames(path):
    """Read `===FRAME===`-delimited animation frames."""
    frames = []
    for chunk in open(path, encoding="utf-8").read().split("===FRAME==="):
        frame = chunk.split("\n")
        while frame and not frame[0].strip():  frame.pop(0)
        while frame and not frame[-1].strip(): frame.pop()
        if frame:
            frames.append(frame)
    return frames


def esc(text):
    return html.escape(text, quote=False)


def wordmark(rows, x, span, top):
    """Paint each glyph at a fixed grid cell so the figure can never reflow,
    whatever monospace font the viewer's browser substitutes."""
    cw = span / max(len(r) for r in rows)
    fs = cw / 0.6
    out = [f'<g fill="url(#wordmark)" font-family="{MONO}" '
           f'font-size="{fs:.2f}" font-weight="700">']
    for r, line in enumerate(rows):
        baseline = top + r * fs + fs * 0.80
        for c, glyph in enumerate(line):
            if glyph != " ":
                out.append(f'<text x="{x + c*cw:.2f}" y="{baseline:.2f}">{esc(glyph)}</text>')
    out.append("</g>")
    return "".join(out)


def ticker(x, y, w, t):
    """A slim candlestick strip: a seeded random walk drawn as green/red OHLC
    candles that scroll right-to-left and bob, looped seamlessly.
    `t` None -> SMIL; otherwise bake the state at time `t`."""
    mid = y + TICKER_H / 2
    amp = TICKER_H / 2 - 2
    price = lambda v: mid - (v - 0.5) * 2 * amp

    rng = random.Random(7)
    candles, last = [], 0.5
    for _ in range(46):
        o = last
        c = min(0.86, max(0.14, o + rng.uniform(-0.20, 0.20)))
        hi = min(0.97, max(o, c) + rng.uniform(0.03, 0.10))
        lo = max(0.03, min(o, c) - rng.uniform(0.03, 0.10))
        candles.append((o, hi, lo, c))
        last = c
    period = len(candles)
    candles = candles + candles                # duplicate -> seamless scroll
    step = w / period
    body_w = max(2.4, step * 0.5)

    glyphs = []
    for i, (o, hi, lo, c) in enumerate(candles):
        cx = x + i * step + step / 2
        colour = UP if c >= o else DOWN
        top, bottom = price(max(o, c)), price(min(o, c))
        candle = (
            f'<line x1="{cx:.1f}" y1="{price(hi):.1f}" x2="{cx:.1f}" y2="{price(lo):.1f}" '
            f'stroke="{colour}" stroke-width="1"/>'
            f'<rect x="{cx-body_w/2:.1f}" y="{top:.1f}" width="{body_w:.1f}" '
            f'height="{max(1.5, bottom-top):.1f}" rx="0.5" fill="{colour}"/>')
        phase = (i % period) * 0.07
        if t is None:
            glyphs.append(
                f'<g><animateTransform attributeName="transform" type="translate" '
                f'values="0 -2.5;0 2.5;0 -2.5" dur="2.4s" begin="-{phase:.2f}s" '
                f'calcMode="spline" keyTimes="0;0.5;1" '
                f'keySplines="0.4 0 0.6 1;0.4 0 0.6 1" repeatCount="indefinite"/>{candle}</g>')
        else:
            bob = -2.5 * math.cos(2 * math.pi * (t + phase) / 2.4)
            glyphs.append(f'<g transform="translate(0 {bob:.2f})">{candle}</g>')

    baseline = (f'<line x1="{x:.1f}" y1="{mid:.1f}" x2="{x+w:.1f}" y2="{mid:.1f}" '
                f'stroke="{RULE}" stroke-width="1" opacity="0.6"/>')
    if t is None:
        scroll = (f'<animateTransform attributeName="transform" type="translate" '
                  f'from="0 0" to="{-w:.1f} 0" dur="20s" repeatCount="indefinite"/>')
    else:
        scroll = f' transform="translate({-(t/LOOP)*w:.1f} 0)"'
        return (baseline + f'<g clip-path="url(#ticker)"><g{scroll}>{"".join(glyphs)}</g></g>')
    return baseline + f'<g clip-path="url(#ticker)"><g>{scroll}{"".join(glyphs)}</g></g>'


def portrait(frames, x, y, line_h, t):
    """Cross-fade the frames with discrete SMIL opacity (a flip-book), or bake
    the single active frame when `t` is given."""
    n = len(frames)
    fs = line_h

    def block(frame):
        out = [f'<text font-family="{MONO}" font-size="{fs:.2f}" fill="url(#portrait)" '
               f'xml:space="preserve" style="white-space:pre">']
        for j, line in enumerate(frame):
            out.append(f'<tspan x="{x:.1f}" y="{y + fs*0.85 + j*line_h:.2f}">{esc(line)}</tspan>')
        out.append("</text>")
        return "".join(out)

    if t is not None:
        return block(frames[int(t % 1.6 / 1.6 * n) % n])

    out = []
    for i, frame in enumerate(frames):
        a, b = i / n, (i + 1) / n
        if i == 0:        keys, vals = f"0;{b:.4f}", "1;0"
        elif i == n - 1:  keys, vals = f"0;{a:.4f}", "0;1"
        else:             keys, vals = f"0;{a:.4f};{b:.4f}", "0;1;0"
        out.append(f'<g opacity="{1 if i == 0 else 0}">'
                   f'<animate attributeName="opacity" calcMode="discrete" dur="1.6s" '
                   f'repeatCount="indefinite" keyTimes="{keys}" values="{vals}"/>'
                   f'{block(frame)}</g>')
    return "".join(out)


def info(x, right, y0):
    """The neofetch-style block: header, dotted-leader rows, a section rule."""
    out, y = [], y0
    for entry in INFO:
        kind = entry[0]
        if kind == "gap":
            y += INFO_LH
            continue
        if kind in ("head", "sect"):
            text = entry[1] if kind == "head" else entry[1].upper()
            size = INFO_FS if kind == "head" else INFO_FS - 2
            weight = "600" if kind == "head" else "400"
            colour = HEADER if kind == "head" else DIM
            spacing = "" if kind == "head" else ' letter-spacing="1.6"'
            width = len(text) * INFO_CW * (1 if kind == "head" else 1.12)
            out.append(f'<text x="{x:.1f}" y="{y:.1f}" font-family="{MONO}" '
                       f'font-size="{size}" font-weight="{weight}"{spacing} '
                       f'fill="{colour}">{esc(text)}</text>')
            out.append(f'<line x1="{x+width+13:.1f}" y1="{y-4:.1f}" x2="{right:.1f}" '
                       f'y2="{y-4:.1f}" stroke="{RULE}" stroke-width="1"/>')
            y += INFO_LH
            continue
        label, value = entry[1], entry[2]
        out.append(f'<text x="{x:.1f}" y="{y:.1f}" font-family="{MONO}" '
                   f'font-size="{INFO_FS}" fill="{LABEL}">{esc(label)}</text>')
        out.append(f'<text x="{right:.1f}" y="{y:.1f}" text-anchor="end" '
                   f'font-family="{MONO}" font-size="{INFO_FS}" fill="{VALUE}">{esc(value)}</text>')
        a = x + len(label) * INFO_CW + 10
        b = right - len(value) * INFO_CW - 10
        if b > a:
            out.append(f'<line x1="{a:.1f}" y1="{y-4:.1f}" x2="{b:.1f}" y2="{y-4:.1f}" '
                       f'stroke="{LEADER}" stroke-width="1.4" stroke-linecap="round" '
                       f'stroke-dasharray="0.5 5"/>')
        y += INFO_LH
    return "".join(out)


def defs(wm_x, wm_span, p_y, t_x, t_y, t_w, animate):
    stops = "".join(f'<stop offset="{o}" stop-color="{c}"/>' for o, c in GRADIENT)
    sheen = ("" if not animate else
             f'<animateTransform attributeName="gradientTransform" type="translate" '
             f'values="{-wm_span*0.25:.0f} 0;{wm_span*0.25:.0f} 0;{-wm_span*0.25:.0f} 0" '
             f'dur="9s" calcMode="spline" keyTimes="0;0.5;1" '
             f'keySplines="0.45 0 0.55 1;0.45 0 0.55 1" repeatCount="indefinite"/>')
    return (
        '<defs>'
        f'<linearGradient id="wordmark" gradientUnits="userSpaceOnUse" '
        f'x1="{wm_x}" y1="0" x2="{wm_x+wm_span:.0f}" y2="0">{stops}{sheen}</linearGradient>'
        f'<linearGradient id="portrait" gradientUnits="userSpaceOnUse" '
        f'x1="0" y1="{p_y:.0f}" x2="0" y2="{p_y+PORTRAIT_H:.0f}">{stops}</linearGradient>'
        f'<radialGradient id="glow" cx="0.5" cy="0.5" r="0.5">'
        f'<stop offset="0" stop-color="{GLOW[0]}" stop-opacity="{GLOW[1]}"/>'
        f'<stop offset="1" stop-color="{GLOW[0]}" stop-opacity="0"/></radialGradient>'
        f'<clipPath id="ticker"><rect x="{t_x:.1f}" y="{t_y-4:.1f}" width="{t_w:.1f}" '
        f'height="{TICKER_H+8:.1f}"/></clipPath>'
        '</defs>')


def render(t=None):
    """Build the panel SVG. `t` None -> SMIL animated; a time in seconds -> the
    single baked frame at that moment (used for GIF assembly)."""
    wm = read_lines("assets/wordmark.txt")
    frames = read_frames("assets/alien-frames.txt")
    p_cols = max(len(l) for f in frames for l in f)
    p_rows = max(len(f) for f in frames)

    p_lh = PORTRAIT_H / p_rows
    p_w = p_cols * p_lh * 0.6
    p_x = PAD + 2

    info_x = p_x + p_w + 52
    info_right = info_x + INFO_W
    info_h = len(INFO) * INFO_LH
    width = info_right + PAD

    wm_x, wm_span = PAD + 4, width - 2 * PAD - 8
    wm_h = len(wm) * (wm_span / max(len(r) for r in wm) / 0.6)

    ticker_x = ticker_w = None
    ticker_y = PAD + wm_h + 14
    content_top = ticker_y + TICKER_H + 24
    content_h = max(PORTRAIT_H, info_h)
    p_y = content_top + (content_h - PORTRAIT_H) / 2
    info_y0 = content_top + (content_h - info_h) / 2 + INFO_FS
    height = content_top + content_h + PAD
    ticker_x, ticker_w = PAD + 4, width - 2 * PAD - 8
    glow_pad = PORTRAIT_H * 0.30

    return f"".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" '
        f'viewBox="0 0 {width:.0f} {height:.0f}" role="img" aria-label="aaditya trades">',
        defs(wm_x, wm_span, p_y, ticker_x, ticker_y, ticker_w, animate=t is None),
        f'<rect x="0.5" y="0.5" width="{width-1:.0f}" height="{height-1:.0f}" rx="12" '
        f'fill="{BG}" stroke="{BORDER}"/>',
        wordmark(wm, wm_x, wm_span, PAD),
        ticker(ticker_x, ticker_y, ticker_w, t),
        f'<rect x="{p_x + p_w/2 - PORTRAIT_H/2 - glow_pad:.1f}" y="{p_y - glow_pad:.1f}" '
        f'width="{PORTRAIT_H + 2*glow_pad:.1f}" height="{PORTRAIT_H + 2*glow_pad:.1f}" '
        f'fill="url(#glow)"/>',
        portrait(frames, p_x, p_y, p_lh, t),
        info(info_x, info_right, info_y0),
        "</svg>",
    ])


def build_gif(out):
    """Bake LOOP seconds of motion into frames and assemble an optimised GIF."""
    n = round(LOOP * FPS)
    with tempfile.TemporaryDirectory() as tmp:
        pngs = []
        for i in range(n):
            svg = os.path.join(tmp, f"{i:03}.svg")
            png = os.path.join(tmp, f"{i:03}.png")
            open(svg, "w", encoding="utf-8").write(render(i / FPS))
            subprocess.run(["rsvg-convert", svg, "-o", png], check=True)
            pngs.append(png)
        subprocess.run(["magick", "-delay", f"{100/FPS:.0f}", "-loop", "0",
                        *pngs, "-layers", "OptimizePlus", out], check=True)


def main():
    if OUT.endswith(".gif"):
        build_gif(OUT)
    else:
        open(OUT, "w", encoding="utf-8").write(render() + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
