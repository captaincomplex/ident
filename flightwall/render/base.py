"""Renderer interface. A renderer takes a Screen and shows it somewhere."""
from __future__ import annotations

from typing import Protocol

from .presenter import Screen


class Renderer(Protocol):
    def show(self, screen: Screen) -> None:
        ...

    def clear(self) -> None:
        ...


def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
