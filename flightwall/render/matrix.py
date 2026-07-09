"""LED matrix renderer for HUB75 panels via hzeller's rpi-rgb-led-matrix.

The Python bindings (``rgbmatrix``) are NOT pip-installable; you build them on
the Pi from https://github.com/hzeller/rpi-rgb-led-matrix (see README). This
module imports them lazily so the rest of the project runs without hardware.

Defaults assume two chained 64x32 HUB75 panels (=128x32) on an Adafruit RGB
Matrix Bonnet. Adjust rows/cols/chain in config to match your panels.
"""
from __future__ import annotations

import os
from typing import Optional

from .base import Renderer, hex_to_rgb
from .presenter import Screen

# BDF fonts ship inside the rpi-rgb-led-matrix repo under fonts/.
DEFAULT_FONT_DIR = "/home/pi/rpi-rgb-led-matrix/fonts"


class MatrixRenderer(Renderer):
    def __init__(self, rows: int = 32, cols: int = 64, chain: int = 2,
                 parallel: int = 1, brightness: int = 60,
                 hardware_mapping: str = "adafruit-hat",
                 font_dir: str = DEFAULT_FONT_DIR, gpio_slowdown: int = 2):
        from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics  # type: ignore

        self.graphics = graphics
        opts = RGBMatrixOptions()
        opts.rows = rows
        opts.cols = cols
        opts.chain_length = chain
        opts.parallel = parallel
        opts.brightness = brightness
        opts.hardware_mapping = hardware_mapping
        opts.gpio_slowdown = gpio_slowdown
        self.matrix = RGBMatrix(options=opts)
        self.canvas = self.matrix.CreateFrameCanvas()
        self.width = cols * chain
        self.height = rows * parallel

        self.f_hdr = self._font(font_dir, "4x6.bdf")
        self.f_main = self._font(font_dir, "6x10.bdf")
        self.f_sub = self._font(font_dir, "5x7.bdf")

    def _font(self, font_dir, name):
        f = self.graphics.Font()
        path = os.path.join(font_dir, name)
        if os.path.exists(path):
            f.LoadFont(path)
        return f

    def show(self, screen: Screen) -> None:
        g = self.graphics
        self.canvas.Clear()
        accent = g.Color(*hex_to_rgb(screen.accent))
        white = g.Color(224, 230, 237)
        dim = g.Color(120, 130, 140)

        g.DrawText(self.canvas, self.f_hdr, 1, 5, accent, screen.header[:30])
        g.DrawText(self.canvas, self.f_main, 1, 15, white,
                   self._fit(screen.line1, self.width, 6))
        g.DrawText(self.canvas, self.f_sub, 1, 23, dim,
                   self._fit(screen.line2, self.width, 5))
        g.DrawText(self.canvas, self.f_sub, 1, 31, accent,
                   self._fit(screen.line3, self.width, 5))

        if screen.progress is not None:
            pw = int((self.width - 2) * screen.progress / 100)
            for x in range(1, self.width - 1):
                col = accent if x <= pw else g.Color(30, 36, 44)
                self.canvas.SetPixel(x, self.height - 1, col.red, col.green, col.blue)

        self.canvas = self.matrix.SwapOnVSync(self.canvas)

    def _fit(self, text: str, width_px: int, char_px: int) -> str:
        return text[: max(0, width_px // char_px)]

    def clear(self) -> None:
        self.matrix.Clear()
