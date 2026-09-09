"""Game-state machine tying the WebSocket connection to the guesser/artist.
One PictionaryBot instance tracks server-driven game state and drives
background guessing/drawing loops for its turn."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from .artist import Artist, FallbackShapeArtist, Stroke
from .canvas import VirtualCanvas
from .client import PictionaryConnection
from .config import BotConfig
from .guesser import Guesser

log = logging.getLogger("ai_player.bot")


class PictionaryBot:
    def __init__(self, config: BotConfig, guesser: Guesser, artist: Artist):
        self.config = config
        self.guesser = guesser
        self.artist = artist

        self.canvas = VirtualCanvas(*config.canvas_size)
        self.connection: Optional[PictionaryConnection] = None

        # Server-driven state.
        self.my_id: Optional[str] = None
        self.room_code: Optional[str] = None
        self.phase: str = "LOBBY"
        self.drawer_id: Optional[str] = None
        self.masked_word: str = ""
        self.seconds_left: int = 0
        self.draw_seconds: int = 0
        self.players: dict[str, dict] = {}
        self.guessed_this_turn: bool = False

        # Per-turn scratch state.
        self._others_wrong_guesses: list[str] = []
        self._pending_word: Optional[str] = None
        self._planned_strokes: Optional[list[Stroke]] = None
        self._plan_task: Optional[asyncio.Task] = None
        self._guess_task: Optional[asyncio.Task] = None
        self._draw_task: Optional[asyncio.Task] = None
        # Created lazily (see `_wake_event`) since asyncio.Event() binds to the
        # running loop on Python 3.9, and the bot is normally constructed before
        # asyncio.run() starts one.
        self._wake_event_: Optional[asyncio.Event] = None

    # ── lifecycle ──────────────────────────────────────────────────────────

    async def run(self) -> None:
        async with PictionaryConnection(self.config.server_url) as conn:
            self.connection = conn
            if self.config.create_room:
                await conn.send({"type": "CREATE_ROOM", "name": self.config.name})
            else:
                await conn.send(
                    {"type": "JOIN_ROOM", "roomCode": self.config.room_code, "name": self.config.name}
                )
            async for ev in conn.messages():
                try:
                    await self._handle(ev)
                except Exception:
                    log.exception("Failed to handle event: %r", ev)

    @property
    def _wake_event(self) -> asyncio.Event:
        if self._wake_event_ is None:
            self._wake_event_ = asyncio.Event()
        return self._wake_event_

    def _is_drawer(self) -> bool:
        return self.my_id is not None and self.drawer_id == self.my_id

    def _should_keep_guessing(self) -> bool:
        return self.phase == "DRAWING" and not self.guessed_this_turn and not self._is_drawer()

    def _cancel_turn_tasks(self) -> None:
        for task in (self._plan_task, self._guess_task, self._draw_task):
            if task is not None and not task.done():
                task.cancel()
        self._plan_task = self._guess_task = self._draw_task = None

    # ── event dispatch ───────────────────────────────────────────────────

    async def _handle(self, ev: dict) -> None:
        ev_type = ev.get("type")
        handler = getattr(self, f"_on_{ev_type.lower()}", None) if ev_type else None
        if handler is not None:
            await handler(ev)
        elif ev_type not in ("DRAW", "LINE", "CLEAR"):
            log.debug("Unhandled event type: %s", ev_type)

        if ev_type in ("DRAW", "LINE", "CLEAR"):
            self.canvas.apply_event(ev)

    async def _on_you_are(self, ev: dict) -> None:
        self.my_id = ev["id"]
        log.info("Connected as player %s", self.my_id)

    async def _on_room_state(self, ev: dict) -> None:
        self.room_code = ev.get("roomCode")
        self.phase = ev.get("phase", self.phase)
        self.players = {p["id"]: p for p in ev.get("players", [])}
        if "drawerId" in ev:
            self.drawer_id = ev["drawerId"]
        if "maskedWord" in ev:
            self.masked_word = ev["maskedWord"]
        if self.room_code:
            log.info("Room code: %s (share this with human players)", self.room_code)

    async def _on_player_joined(self, ev: dict) -> None:
        log.info("%s joined the room", ev.get("name"))

    async def _on_player_left(self, ev: dict) -> None:
        log.info("%s left the room", ev.get("name"))

    async def _on_game_started(self, ev: dict) -> None:
        log.info("Game started!")

    async def _on_turn_start(self, ev: dict) -> None:
        self._cancel_turn_tasks()
        self.phase = "PICKING_WORD"
        self.drawer_id = ev.get("drawerId")
        self.masked_word = ""
        self.guessed_this_turn = False
        self._others_wrong_guesses = []
        self._pending_word = None
        self._planned_strokes = None
        self.canvas.clear()

        drawer_name = ev.get("drawerName")
        if self._is_drawer():
            log.info("Round %s of %s, my turn to draw!", ev.get("round"), ev.get("totalRounds"))
        else:
            log.info("Round %s of %s, %s is drawing", ev.get("round"), ev.get("totalRounds"), drawer_name)

    async def _on_word_options(self, ev: dict) -> None:
        options = ev.get("words", [])
        word = await self.artist.pick_word(options)
        self._pending_word = word
        log.info("Picking word: %s (from %s)", word, options)
        await self.connection.send({"type": "WORD_CHOICE", "word": word})
        # Plan while the server's word-pick window (and then the pre-draw setup) elapses,
        # so the stroke plan is usually ready before WORD_SELECTED arrives.
        self._plan_task = asyncio.create_task(self._plan_strokes(word))

    async def _plan_strokes(self, word: str) -> None:
        try:
            self._planned_strokes = await self.artist.plan_strokes(word)
        except Exception:
            log.exception("Stroke planning failed for %r, using fallback shape", word)
            self._planned_strokes = FallbackShapeArtist().plan_strokes_sync(word)

    async def _on_your_word(self, ev: dict) -> None:
        log.info("Confirmed word: %s", ev.get("word"))

    async def _on_word_selected(self, ev: dict) -> None:
        self.phase = "DRAWING"
        self.masked_word = ev.get("maskedWord", "")
        self.draw_seconds = ev.get("drawSeconds", 80)

        if self._is_drawer():
            self._draw_task = asyncio.create_task(self._execute_drawing())
        else:
            self._guess_task = asyncio.create_task(self._guess_loop())

    async def _on_timer_tick(self, ev: dict) -> None:
        self.seconds_left = ev.get("secondsLeft", self.seconds_left)

    async def _on_letter_reveal(self, ev: dict) -> None:
        self.masked_word = ev.get("maskedWord", self.masked_word)
        self._wake_event.set()

    async def _on_chat_message(self, ev: dict) -> None:
        kind = ev.get("kind")
        if kind == "correct":
            if ev.get("fromId") == self.my_id:
                self.guessed_this_turn = True
                log.info("Correct! (+%s points)", ev.get("points"))
            else:
                log.info("%s guessed it (+%s points)", ev.get("fromName"), ev.get("points"))
        elif kind in ("normal", "close") and self.phase == "DRAWING":
            text = ev.get("text")
            if text:
                self._others_wrong_guesses.append(text)

    async def _on_score_update(self, ev: dict) -> None:
        for s in ev.get("scores", []):
            if s["id"] in self.players:
                self.players[s["id"]]["score"] = s["score"]

    async def _on_turn_end(self, ev: dict) -> None:
        self._cancel_turn_tasks()
        self.phase = "TURN_END"
        log.info("Turn over (%s). The word was %s", ev.get("reason"), ev.get("word"))

    async def _on_game_over(self, ev: dict) -> None:
        self._cancel_turn_tasks()
        self.phase = "GAME_OVER"
        scores = ev.get("scores", [])
        log.info("Game over! Final scores: %s", ", ".join(f"{s['name']}={s['score']}" for s in scores))

    async def _on_error(self, ev: dict) -> None:
        log.warning("Server error: %s", ev.get("message"))

    # ── guessing ─────────────────────────────────────────────────────────

    async def _guess_loop(self) -> None:
        tried: list[str] = []
        try:
            await self._sleep_or_wake(self.config.min_seconds_before_first_guess)
            attempts = 0
            while attempts < self.config.max_guesses_per_turn:
                if not self._should_keep_guessing():
                    return
                if self.canvas.is_blank():
                    await self._sleep_or_wake(1.0)
                    continue

                try:
                    already_tried = tried + self._others_wrong_guesses
                    guess = await self.guesser.guess(self.canvas.png_bytes(), self.masked_word, already_tried)
                except Exception:
                    log.exception("Guesser failed, backing off")
                    await self._sleep_or_wake(self.config.guess_cooldown_seconds)
                    continue

                attempts += 1
                if guess and guess.lower() not in {t.lower() for t in tried}:
                    tried.append(guess)
                    log.info("Guessing: %s", guess)
                    await self.connection.send({"type": "CHAT_GUESS", "text": guess})

                await self._sleep_or_wake(self.config.guess_cooldown_seconds)
        except asyncio.CancelledError:
            pass

    async def _sleep_or_wake(self, timeout: float) -> None:
        """Sleep up to `timeout`, waking early if a LETTER_REVEAL gives new info."""
        self._wake_event.clear()
        try:
            await asyncio.wait_for(self._wake_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass

    # ── drawing ──────────────────────────────────────────────────────────

    async def _execute_drawing(self) -> None:
        try:
            if self._plan_task is not None:
                await self._plan_task
            strokes = self._planned_strokes or FallbackShapeArtist().plan_strokes_sync(self._pending_word or "")

            width, height = self.config.canvas_size
            budget_seconds = max(5.0, self.draw_seconds * self.config.draw_time_budget_fraction)
            total_points = sum(len(s) for s in strokes) or 1
            delay = max(0.03, min(0.5, budget_seconds / total_points))

            for stroke in strokes:
                first = True
                for (nx, ny) in stroke:
                    await self.connection.send(
                        {
                            "type": "DRAW",
                            "x": round(nx * width, 1),
                            "y": round(ny * height, 1),
                            "color": "#1a1a1e",
                            "brushSize": 5,
                            "startStroke": first,
                        }
                    )
                    first = False
                    await asyncio.sleep(delay)
            log.info("Finished drawing %r (%d strokes)", self._pending_word, len(strokes))
        except asyncio.CancelledError:
            pass
        except Exception:
            log.exception("Drawing execution failed")
