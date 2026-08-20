"""Vestaboard renderer (split-flap board, 6 rows x 22 columns).

A Vestaboard is a grid of 132 mechanical character "Bits". It can show letters,
digits, basic punctuation and seven colour chips - no free-form graphics - and
each change physically flips, so updates are slow and rate-limited. That makes
it a great fit for the *text* states of this project (next duty, report time,
home time) and a poor fit for a smooth live map; the route is reduced to a
coarse progress track built from chips.

Two transports:
  * Read/Write API (cloud)  - needs a Read/Write key (Settings -> API in the app)
  * Local API (LAN)         - needs the board's IP + a Local API key; faster,
                              works offline, but you must keep app transitions off

We only push when the rendered board actually changes, and no more than once
every few seconds, to respect the hardware and the API limits.
"""
from __future__ import annotations

import time
from typing import Optional

import requests

from .base import Renderer
from .presenter import Screen

ROWS, COLS = 6, 22

# Vestaboard character codes.
_PUNCT = {" ": 0, "!": 37, "@": 38, "#": 39, "$": 40, "(": 41, ")": 42,
          "-": 44, "+": 46, "&": 47, "=": 48, ";": 49, ":": 50, "'": 52,
          '"': 53, "%": 54, ",": 55, ".": 56, "/": 59, "?": 60, "\u00b0": 62}
# Colour chips: red orange yellow green blue violet white.
CHIP = {"red": 63, "orange": 64, "yellow": 65, "green": 66, "blue": 67,
        "violet": 68, "white": 69}
_ACCENT_CHIP = {"#39c0ff": 67, "#ffb340": 64, "#ffd000": 65, "#7ee787": 66,
                "#c08cff": 68, "#ff7b72": 63, "#8b949e": 69}


def _code(ch: str) -> int:
    if ch.isalpha():
        return ord(ch.upper()) - 64
    if ch.isdigit():
        return 36 if ch == "0" else 26 + int(ch)
    return _PUNCT.get(ch, 0)


def _row(text: str, justify: str = "left") -> list[int]:
    text = (text or "").replace("\u2192", "-")[:COLS]
    cells = [_code(c) for c in text]
    pad = COLS - len(cells)
    if justify == "right":
        return [0] * pad + cells
    if justify == "center":
        l = pad // 2
        return [0] * l + cells + [0] * (pad - l)
    return cells + [0] * pad


def _split_row(left: str, right: str) -> list[int]:
    left, right = left[:COLS], right[:COLS]
    gap = COLS - len(left) - len(right)
    if gap < 1:
        return _row((left + " " + right))
    return [_code(c) for c in left] + [0] * gap + [_code(c) for c in right]


def _track_row(dep: str, arr: str, progress: Optional[float], chip: int) -> list[int]:
    p = 0.0 if progress is None else max(0.0, min(100.0, progress)) / 100.0
    inner = COLS - 8                      # "LGW " + track + " SKG"
    pos = round(p * (inner - 1))
    track = []
    for i in range(inner):
        track.append(chip if i == pos else (_code("=") if i < pos else _code("-")))
    return ([_code(c) for c in f"{dep:<3} "] + track + [_code(c) for c in f" {arr:>3}"])[:COLS]


def grid_for(screen: Screen) -> list[list[int]]:
    chip = _ACCENT_CHIP.get(screen.accent, 69)
    rows = [[0] * COLS for _ in range(ROWS)]

    if screen.arc:
        dep, arr, progress = screen.arc
        flight_id = screen.line1.split(" ")[0] if screen.line1 else ""
        land = screen.line2.replace("  ", " ").strip()
        home = ("HOME " + screen.line3.split("HOME", 1)[1].strip()
                if "HOME" in screen.line3 else "")
        rows[0] = _split_row(screen.header, flight_id)
        rows[2] = _track_row(dep, arr, progress, chip)
        rows[4] = _split_row(land, home)
    else:
        rows[0] = _row(screen.header, "center")
        rows[1] = _row(screen.line1)
        rows[3] = _row(screen.line2)
        home = ("HOME " + screen.line3.split("HOME", 1)[1].strip()
                if "HOME" in screen.line3 else screen.line3)
        rows[4] = _row(home)
    return rows


class VestaboardRenderer(Renderer):
    def __init__(self, rw_key: str = "", local_ip: str = "", local_key: str = "",
                 min_interval: float = 15.0, timeout: float = 10.0):
        self.rw_key = rw_key
        self.local_ip = local_ip
        self.local_key = local_key
        self.min_interval = min_interval
        self.timeout = timeout
        self._last_grid = None
        self._last_send = 0.0

    def show(self, screen: Screen) -> None:
        grid = grid_for(screen)
        if grid == self._last_grid:
            return
        if time.time() - self._last_send < self.min_interval:
            return
        if self._post(grid):
            self._last_grid = grid
            self._last_send = time.time()

    def _post(self, grid) -> bool:
        try:
            if self.local_ip and self.local_key:
                url = f"http://{self.local_ip}:7000/local-api/message"
                headers = {"X-Vestaboard-Local-Api-Key": self.local_key}
            elif self.rw_key:
                url = "https://rw.vestaboard.com/"
                headers = {"X-Vestaboard-Read-Write-Key": self.rw_key}
            else:
                return False
            headers["Content-Type"] = "application/json"
            resp = requests.post(url, json={"characters": grid}, headers=headers,
                                 timeout=self.timeout)
            resp.raise_for_status()
            return True
        except Exception as e:
            print(f"[vestaboard] post failed: {e}")
            return False

    def clear(self) -> None:
        self._post([[0] * COLS for _ in range(ROWS)])
