"""A virtual canvas that replays the game's DRAW / LINE / CLEAR events.

Mirrors the rendering logic in pictionary.html's `applyDraw` / `applyLine` /
`clearCanvas` closely enough to produce a reasonable raster snapshot for a
vision model to look at — it doesn't need to be pixel-perfect, just legible.
"""

from __future__ import annotations

import base64
import io
import time
from typing import Optional

from PIL import Image, ImageDraw


class VirtualCanvas:
    def __init__(self, width: int = 1000, height: int = 700):
        self.width = width
        self.height = height
        self._image = Image.new("RGB", (width, height), "white")
        self._draw = ImageDraw.Draw(self._image)
        self._last_point: Optional[tuple[float, float]] = None
        self.stroke_count = 0
        self.last_activity: Optional[float] = None

    def apply_event(self, ev: dict) -> None:
        """Feed one server-relayed DRAW / LINE / CLEAR event."""
        ev_type = ev.get("type")
        if ev_type == "CLEAR":
            self.clear()
        elif ev_type == "DRAW":
            self._apply_draw(ev)
        elif ev_type == "LINE":
            self._apply_line(ev)

    def clear(self) -> None:
        self._image = Image.new("RGB", (self.width, self.height), "white")
        self._draw = ImageDraw.Draw(self._image)
        self._last_point = None
        self.stroke_count = 0
        self.last_activity = time.monotonic()

    def _clamp(self, x: float, y: float) -> tuple[float, float]:
        return (max(0.0, min(self.width, x)), max(0.0, min(self.height, y)))

    def _apply_draw(self, ev: dict) -> None:
        x, y = self._clamp(float(ev.get("x", 0)), float(ev.get("y", 0)))
        color = ev.get("color") or "#1a1a1e"
        width = max(1, round(float(ev.get("brushSize", 4) or 4)))

        if ev.get("startStroke"):
            self._last_point = (x, y)
            # A lone dot (pointerdown with no drag) should still show up.
            r = width / 2
            self._draw.ellipse([x - r, y - r, x + r, y + r], fill=color)
        else:
            if self._last_point is not None:
                self._draw.line([self._last_point, (x, y)], fill=color, width=width)
                # Round the joint so a fast, sharp-angled stroke doesn't look gappy.
                r = width / 2
                self._draw.ellipse([x - r, y - r, x + r, y + r], fill=color)
            self._last_point = (x, y)

        self.stroke_count += 1
        self.last_activity = time.monotonic()

    def _apply_line(self, ev: dict) -> None:
        x1, y1 = self._clamp(float(ev.get("x", 0)), float(ev.get("y", 0)))
        x2, y2 = self._clamp(float(ev.get("x2", 0)), float(ev.get("y2", 0)))
        color = ev.get("color") or "#1a1a1e"
        width = max(1, round(float(ev.get("brushSize", 4) or 4)))

        self._draw.line([(x1, y1), (x2, y2)], fill=color, width=width)
        for (cx, cy) in ((x1, y1), (x2, y2)):
            r = width / 2
            self._draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)

        self.stroke_count += 1
        self.last_activity = time.monotonic()
        self._last_point = None

    def is_blank(self) -> bool:
        return self.stroke_count == 0

    def png_bytes(self) -> bytes:
        buf = io.BytesIO()
        self._image.save(buf, format="PNG")
        return buf.getvalue()

    def base64_png(self) -> str:
        return base64.b64encode(self.png_bytes()).decode("ascii")
