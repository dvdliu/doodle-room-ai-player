"""Bot configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BotConfig:
    server_url: str = "ws://localhost:8081"
    name: str = "Claude"

    # Exactly one of these drives how the bot enters a game.
    room_code: Optional[str] = None
    create_room: bool = False

    # Anthropic API. If offline=True, the bot never calls the API — it uses the
    # built-in heuristic guesser/artist instead, which is handy for demos, tests,
    # or trying the bot without burning API credits.
    offline: bool = False
    anthropic_api_key: Optional[str] = None
    model: str = "claude-sonnet-5"

    # Virtual canvas size used to replay DRAW/LINE/CLEAR events. The real game's
    # coordinates are relative to whatever size the sending browser's canvas
    # happened to be, so this is a best-effort approximation, not an exact match.
    canvas_size: tuple[int, int] = (1000, 700)

    # Guessing pace.
    guess_cooldown_seconds: float = 4.0
    min_seconds_before_first_guess: float = 2.5
    max_guesses_per_turn: int = 25

    # Drawing pace: spend at most this fraction of the turn's drawSeconds actually
    # sketching, leaving the rest as a buffer against slow strokes/lag.
    draw_time_budget_fraction: float = 0.75

    extra_log_events: bool = field(default=False)
