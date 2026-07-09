"""Hardware-free renderer.

Prints an ASCII panel to the console (useful in logs / headless dev) and can
produce a PNG that looks like the LED wall for the web preview. Lets you build
and run the whole system before any panels arrive.

Two layouts:
  * "full"    - 128x32, uses a route-arc map while airborne
  * "compact" - 64x32, abbreviated (route scrolls on real hardware)
"""
from __future__ import annotations

import io
import math
from typing import Optional

from .base import Renderer, hex_to_rgb
from .presenter import Screen


class ConsoleSimulator(Renderer):
    def show(self, screen: Screen) -> None:
        width = 46
        bar = "+" + "-" * width + "+"
        lines = [screen.header, screen.line1, screen.line2, screen.line3]
        print("\n" + bar)
        for i, ln in enumerate(lines):
            marker = "*" if i == 0 else " "
            print(f"|{marker}{ln[:width-1].ljust(width-1)}|")
        if screen.progress is not None:
            filled = int(width * screen.progress / 100)
            print("|" + "#" * filled + "." * (width - filled) + "|")
        if screen.flags:
            print(f"|{(' / '.join(screen.flags))[:width].ljust(width)}|")
        print(bar)

    def clear(self) -> None:
        print("\033[2J", end="")


def render_png(screen: Screen, cols: int = 128, rows: int = 32, scale: int = 6,
               layout: str = "full") -> Optional[bytes]:
    """Render the screen to a PNG styled like an LED matrix. Needs Pillow."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        return None

    W, H = cols * scale, rows * scale
    img = Image.new("RGB", (W, H), (8, 10, 14))
    draw = ImageDraw.Draw(img)

    def font(px):
        for name in ("DejaVuSansMono.ttf", "DejaVuSans.ttf"):
            try:
                return ImageFont.truetype(name, max(6, px))
            except Exception:
                continue
        return ImageFont.load_default()

    accent = hex_to_rgb(screen.accent)
    white = (226, 232, 240)
    dim = (132, 144, 158)
    pad = 3 * scale

    def text_w(s, f):
        return draw.textlength(s, font=f)

    def fit(s, f, maxw):
        while s and text_w(s, f) > maxw:
            s = s[:-1]
        return s

    def right(s, f, y, fill, edge=None):
        edge = W - pad if edge is None else edge
        draw.text((edge - text_w(s, f), y), s, font=f, fill=fill)

    compact = layout == "compact" or cols <= 64

    if screen.arc and not compact:
        _draw_arc_layout(draw, screen, W, H, scale, pad, font, accent, white, dim,
                         fit, text_w, right)
    elif screen.arc and compact:
        _draw_compact_arc(draw, screen, W, H, scale, pad, font, accent, white, dim,
                          fit, text_w)
    else:
        _draw_text_layout(draw, screen, W, H, scale, pad, font, accent, white, dim,
                          fit, text_w, right, compact)

    for gx in range(0, W, scale):
        draw.line([(gx, 0), (gx, H)], fill=(5, 6, 9))
    for gy in range(0, H, scale):
        draw.line([(0, gy), (W, gy)], fill=(5, 6, 9))

    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def _draw_arc_layout(draw, s, W, H, scale, pad, font, accent, white, dim,
                     fit, text_w, right):
    dep, arr, progress = s.arc
    p = 0.0 if progress is None else max(0.0, min(100.0, progress)) / 100.0

    f_tag = font(int(H * 0.16))
    f_id = font(int(H * 0.18))
    f_lbl = font(int(H * 0.15))
    f_time = font(int(H * 0.16))

    draw.text((pad, int(H * 0.03)), s.header, font=f_tag, fill=accent)
    flight_id = s.line1.split(" ")[0] if s.line1 else ""
    right(flight_id, f_id, int(H * 0.02), white)

    ax0, ax1 = pad + 2 * scale, W - pad - 2 * scale
    base_y = int(H * 0.62)
    amp = int(H * 0.22)

    def arc_pt(t):
        return (ax0 + (ax1 - ax0) * t, base_y - amp * math.sin(math.pi * t))

    prev = arc_pt(0.0)
    steps = 64
    for i in range(1, steps + 1):
        t = i / steps
        cur = arc_pt(t)
        col = accent if t <= p else (54, 64, 76)
        draw.line([prev, cur], fill=col, width=max(1, scale // 3))
        prev = cur

    for t, code in ((0.0, dep), (1.0, arr)):
        x, y = arc_pt(t)
        r = max(2, int(scale * 0.7))
        draw.ellipse([x - r, y - r, x + r, y + r], fill=white)
    draw.text((ax0 - scale, base_y + int(scale * 0.6)), dep, font=f_lbl, fill=dim)
    right(arr, f_lbl, base_y + int(scale * 0.6), dim, edge=ax1 + scale)

    px, py = arc_pt(p)
    r = max(2, int(scale * 0.9))
    draw.ellipse([px - r, py - r, px + r, py + r], fill=accent)
    draw.ellipse([px - r - scale // 2, py - r - scale // 2,
                  px + r + scale // 2, py + r + scale // 2],
                 outline=accent, width=1)

    land = s.line2.replace("  ", " ")
    home = ""
    if "HOME" in s.line3:
        home = "HOME " + s.line3.split("HOME", 1)[1].strip()
    draw.text((pad, int(H * 0.82)), fit(land, f_time, W * 0.5), font=f_time, fill=white)
    if home:
        right(home, f_time, int(H * 0.82), accent)


def _draw_text_layout(draw, s, W, H, scale, pad, font, accent, white, dim,
                      fit, text_w, right, compact):
    f_hdr = font(int(H * (0.14 if not compact else 0.16)))
    f_main = font(int(H * (0.23 if not compact else 0.20)))
    f_sub = font(int(H * (0.155 if not compact else 0.15)))

    draw.text((pad, int(H * 0.04)), fit(s.header, f_hdr, W - 2 * pad), font=f_hdr, fill=accent)
    draw.text((pad, int(H * 0.26)), fit(s.line1, f_main, W - 2 * pad), font=f_main, fill=white)

    y2 = int(H * 0.56)
    draw.text((pad, y2), fit(s.line2, f_sub, W * 0.62), font=f_sub, fill=dim)
    if "HOME" in s.line3:
        home = "HOME " + s.line3.split("HOME", 1)[1].strip()
        rtn = s.line3.split("HOME", 1)[0].strip()
        right(home, f_sub, y2, accent)
        if rtn:
            draw.text((pad, int(H * 0.74)), fit(rtn, f_sub, W - 2 * pad),
                      font=f_sub, fill=dim)
    else:
        draw.text((pad, int(H * 0.74)), fit(s.line3, f_sub, W - 2 * pad),
                  font=f_sub, fill=accent)


def _draw_compact_arc(draw, s, W, H, scale, pad, font, accent, white, dim,
                      fit, text_w):
    dep, arr, progress = s.arc
    p = 0.0 if progress is None else max(0.0, min(100.0, progress)) / 100.0
    f_id = font(int(H * 0.17))
    f_sub = font(int(H * 0.15))

    flight_id = s.line1.split(" ")[0] if s.line1 else ""
    draw.text((pad, int(H * 0.02)), fit(f"{flight_id} {dep}\u2192{arr}",
              f_id, W - 2 * pad), font=f_id, fill=white)
    # Straight progress track.
    y = int(H * 0.40)
    x0, x1 = pad, W - pad
    draw.line([(x0, y), (x1, y)], fill=(54, 64, 76), width=max(1, scale // 3))
    draw.line([(x0, y), (x0 + (x1 - x0) * p, y)], fill=accent, width=max(1, scale // 3))
    mx = x0 + (x1 - x0) * p
    r = max(2, int(scale * 0.6))
    draw.ellipse([mx - r, y - r, mx + r, y + r], fill=accent)
    # Stacked, full-width: too narrow for side-by-side at 64px.
    land = s.line2.split("  ")[0].strip()
    draw.text((pad, int(H * 0.56)), fit(land, f_sub, W - 2 * pad), font=f_sub, fill=white)
    if "HOME" in s.line3:
        home = "HOME " + s.line3.split("HOME", 1)[1].strip()
        draw.text((pad, int(H * 0.77)), fit(home, f_sub, W - 2 * pad),
                  font=f_sub, fill=accent)
