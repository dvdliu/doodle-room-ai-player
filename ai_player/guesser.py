"""Strategies for turning a canvas snapshot into a guess. `ClaudeVisionGuesser`
is the real thing; `HeuristicGuesser` is a zero-cost offline fallback used in
--offline mode and in tests."""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from typing import Optional, Sequence

_FALLBACK_VOCAB = [
    "apple", "banana", "sun", "moon", "star", "tree", "house", "car", "dog", "cat",
    "fish", "bird", "ball", "book", "chair", "table", "cup", "hat", "shoe", "cloud",
    "rain", "snow", "fire", "boat", "cake", "egg", "door", "key", "box", "flower",
    "grass", "bed", "phone", "clock", "spoon", "guitar", "umbrella", "bicycle",
    "robot", "dinosaur", "castle", "rainbow", "spider", "penguin", "rocket",
    "volcano", "skateboard", "telescope", "waterfall", "campfire", "jellyfish",
    "kangaroo", "lighthouse", "snowman", "octopus", "pumpkin", "dragon", "mermaid",
]


def _non_space_length(masked_word: str) -> int:
    """Letter count of a masked word, e.g. 'a__le' -> 5. Spaces (revealed as-is
    for multi-word phrases) don't count as letters; underscores do, since each
    stands in for one still-hidden letter."""
    return sum(1 for c in masked_word if c != " ")


class Guesser(ABC):
    @abstractmethod
    async def guess(
        self,
        image_png: bytes,
        masked_word: str,
        already_tried: Sequence[str],
    ) -> Optional[str]:
        """Return a single guess word/phrase, or None to pass this round."""
        raise NotImplementedError


class ClaudeVisionGuesser(Guesser):
    """Shows Claude the current canvas and asks it to guess the word."""

    def __init__(self, client, model: str = "claude-sonnet-5"):
        self._client = client
        self._model = model

    async def guess(
        self,
        image_png: bytes,
        masked_word: str,
        already_tried: Sequence[str],
    ) -> Optional[str]:
        import base64

        length_hint = f"It's {_non_space_length(masked_word)} letters long." if masked_word else ""
        pattern_hint = ""
        if masked_word and "_" in masked_word and any(c != "_" for c in masked_word):
            pattern_hint = f" The revealed letter pattern so far is: {masked_word}"

        avoid = f" Do not repeat any of these already-wrong guesses: {', '.join(already_tried)}." if already_tried else ""

        prompt = (
            "You're playing Pictionary as a guesser. The image is someone's in-progress "
            "sketch of a single English word or short common phrase. "
            f"{length_hint}{pattern_hint}{avoid} "
            "Reply with ONLY your single best-guess word or short phrase — no punctuation, "
            "no explanation, no extra words. If the sketch is too sparse to tell yet, reply "
            "with exactly: PASS"
        )

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=20,
            temperature=0.4,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": base64.b64encode(image_png).decode("ascii"),
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )

        text = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        ).strip()
        return _clean_guess(text)


class HeuristicGuesser(Guesser):
    """Offline fallback: picks a random word matching the known mask length/letters."""

    def __init__(self, vocab: Optional[Sequence[str]] = None, rng: Optional[random.Random] = None):
        self._vocab = list(vocab) if vocab else list(_FALLBACK_VOCAB)
        self._rng = rng or random.Random()

    async def guess(
        self,
        image_png: bytes,
        masked_word: str,
        already_tried: Sequence[str],
    ) -> Optional[str]:
        tried_lower = {t.lower() for t in already_tried}
        candidates = [w for w in self._vocab if w.lower() not in tried_lower]

        if masked_word:
            target_len = len(masked_word)
            by_length = [w for w in candidates if len(w) == target_len]
            if by_length:
                candidates = by_length

            revealed = {i: c for i, c in enumerate(masked_word) if c != "_" and c.isalpha()}
            if revealed:
                matching = [
                    w for w in candidates
                    if len(w) == len(masked_word)
                    and all(w[i].lower() == c.lower() for i, c in revealed.items())
                ]
                if matching:
                    candidates = matching

        if not candidates:
            return None
        return self._rng.choice(candidates)


def _clean_guess(text: str) -> Optional[str]:
    text = text.strip().strip(".!?\"'").strip()
    if not text or text.upper() == "PASS":
        return None
    # Guard against the model ignoring instructions and returning a sentence —
    # keep only the first line/clause, capped to a sane length.
    text = text.splitlines()[0].split(".")[0].strip()
    return text[:60] or None
