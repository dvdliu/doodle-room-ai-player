"""Strategies for turning a word into a stroke plan (a list of (x, y) point
lists in 0..1 canvas space) the bot can draw. `ClaudeStrokeArtist` asks Claude
to design a sketch; `FallbackShapeArtist` guarantees a turn always produces
something."""

from __future__ import annotations

import json
import random
import re
from abc import ABC, abstractmethod
from typing import List, Optional, Sequence, Tuple

Point = Tuple[float, float]
Stroke = List[Point]

_MAX_STROKES = 12
_MAX_POINTS_PER_STROKE = 24


class Artist(ABC):
    @abstractmethod
    async def plan_strokes(self, word: str) -> List[Stroke]:
        """Return a list of strokes (each a list of normalized (x, y) points)."""
        raise NotImplementedError

    @abstractmethod
    async def pick_word(self, options: Sequence[str]) -> str:
        """Choose which of the offered WORD_OPTIONS to draw."""
        raise NotImplementedError


class ClaudeStrokeArtist(Artist):
    """Asks Claude to design a simple recognizable line-art sketch as JSON."""

    def __init__(self, client, model: str = "claude-sonnet-5"):
        self._client = client
        self._model = model

    async def pick_word(self, options: Sequence[str]) -> str:
        # Shorter words are cheaper to sketch clearly in the time budget and
        # tend to be more concrete/drawable (Doodle Room's word bank skews
        # longer for its "hard" category) — no API call needed for this part.
        return min(options, key=len)

    async def plan_strokes(self, word: str) -> List[Stroke]:
        prompt = (
            f'Design a simple line-art sketch of "{word}" for a Pictionary-style drawing game, '
            f"as a JSON stroke plan. Rules:\n"
            f"- Output ONLY JSON, no prose, no markdown fences.\n"
            f'- Shape: {{"strokes": [[[x, y], [x, y], ...], ...]}}\n'
            f"- x and y are floats from 0.0 to 1.0 (0,0 is top-left, 1,1 is bottom-right).\n"
            f"- Each inner list is one continuous pen stroke (points connected in order).\n"
            f"- Use at most {_MAX_STROKES} strokes and at most {_MAX_POINTS_PER_STROKE} points per stroke.\n"
            f"- Use simple recognizable shapes (lines, curves, circles approximated by points). "
            f"No text or letters — this must be guessed visually."
        )
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=2000,
            temperature=0.6,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )
        strokes = parse_stroke_json(text)
        return strokes if strokes else FallbackShapeArtist().plan_strokes_sync(word)


class FallbackShapeArtist(Artist):
    """No API calls — draws a generic placeholder shape so a turn never stalls."""

    def __init__(self, rng: Optional[random.Random] = None):
        self._rng = rng or random.Random()

    async def pick_word(self, options: Sequence[str]) -> str:
        return self._rng.choice(list(options))

    async def plan_strokes(self, word: str) -> List[Stroke]:
        return self.plan_strokes_sync(word)

    def plan_strokes_sync(self, word: str) -> List[Stroke]:
        # A generic house-ish/blob shape. Not meant to be a good guess-inducer —
        # just something that keeps the game moving when the real artist is
        # unavailable or returns something unusable.
        return [
            [(0.3, 0.6), (0.3, 0.9), (0.7, 0.9), (0.7, 0.6)],
            [(0.3, 0.6), (0.5, 0.35), (0.7, 0.6)],
            [(0.45, 0.9), (0.45, 0.72), (0.55, 0.72), (0.55, 0.9)],
        ]


def parse_stroke_json(text: str) -> List[Stroke]:
    """Best-effort extraction of a {"strokes": [...]} payload from model output."""
    text = text.strip()
    # Strip ```json ... ``` fences if the model added them despite instructions.
    fence_match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)

    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return []
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []

    raw_strokes = data.get("strokes")
    if not isinstance(raw_strokes, list):
        return []

    strokes: List[Stroke] = []
    for raw_stroke in raw_strokes[:_MAX_STROKES]:
        if not isinstance(raw_stroke, list):
            continue
        stroke: Stroke = []
        for point in raw_stroke[:_MAX_POINTS_PER_STROKE]:
            if (
                isinstance(point, (list, tuple))
                and len(point) == 2
                and all(isinstance(v, (int, float)) for v in point)
            ):
                x, y = float(point[0]), float(point[1])
                stroke.append((max(0.0, min(1.0, x)), max(0.0, min(1.0, y))))
        if len(stroke) >= 2:
            strokes.append(stroke)

    return strokes
