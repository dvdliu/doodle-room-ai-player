import asyncio
import random

from ai_player.artist import FallbackShapeArtist
from ai_player.bot import PictionaryBot
from ai_player.config import BotConfig
from ai_player.guesser import HeuristicGuesser


class FakeConnection:
    def __init__(self):
        self.sent: list[dict] = []

    async def send(self, payload: dict) -> None:
        self.sent.append(payload)


def make_bot(**overrides) -> tuple[PictionaryBot, FakeConnection]:
    config = BotConfig(
        min_seconds_before_first_guess=0.0,
        guess_cooldown_seconds=0.01,
        max_guesses_per_turn=1,
        **overrides,
    )
    bot = PictionaryBot(config, HeuristicGuesser(rng=random.Random(0)), FallbackShapeArtist())
    conn = FakeConnection()
    bot.connection = conn
    return bot, conn


async def _drive(bot: PictionaryBot, events: list[dict]) -> None:
    for ev in events:
        await bot._handle(ev)


def test_bot_ignores_its_own_turn_for_guessing():
    bot, _ = make_bot()

    async def body():
        await _drive(
            bot,
            [
                {"type": "YOU_ARE", "id": "me"},
                {"type": "TURN_START", "drawerId": "me", "round": 1, "totalRounds": 1},
            ],
        )
        assert bot._should_keep_guessing() is False

    asyncio.run(body())


def test_bot_guesses_when_someone_else_draws():
    bot, conn = make_bot()

    async def body():
        await _drive(
            bot,
            [
                {"type": "YOU_ARE", "id": "me"},
                {"type": "TURN_START", "drawerId": "other", "round": 1, "totalRounds": 1},
                {"type": "WORD_SELECTED", "maskedWord": "___", "drawSeconds": 80},
                {"type": "DRAW", "x": 5, "y": 5, "color": "#000", "brushSize": 4, "startStroke": True},
            ],
        )
        # Let the background guess loop run at least one iteration.
        for _ in range(20):
            await asyncio.sleep(0.02)
            if any(m.get("type") == "CHAT_GUESS" for m in conn.sent):
                break
        assert any(m.get("type") == "CHAT_GUESS" for m in conn.sent)
        bot._cancel_turn_tasks()

    asyncio.run(body())


def test_correct_guess_stops_further_guessing():
    bot, _ = make_bot()

    async def body():
        await _drive(
            bot,
            [
                {"type": "YOU_ARE", "id": "me"},
                {"type": "TURN_START", "drawerId": "other", "round": 1, "totalRounds": 1},
                {"type": "WORD_SELECTED", "maskedWord": "___", "drawSeconds": 80},
                {"type": "CHAT_MESSAGE", "kind": "correct", "fromId": "me", "points": 100},
            ],
        )
        assert bot.guessed_this_turn is True
        assert bot._should_keep_guessing() is False
        bot._cancel_turn_tasks()

    asyncio.run(body())


def test_turn_end_resets_and_cancels_tasks_cleanly():
    bot, _ = make_bot()

    async def body():
        await _drive(
            bot,
            [
                {"type": "YOU_ARE", "id": "me"},
                {"type": "TURN_START", "drawerId": "other", "round": 1, "totalRounds": 1},
                {"type": "WORD_SELECTED", "maskedWord": "___", "drawSeconds": 80},
                {"type": "TURN_END", "reason": "timeout", "word": "cat"},
            ],
        )
        assert bot.phase == "TURN_END"
        assert bot._guess_task is None

    asyncio.run(body())


def test_other_players_wrong_guesses_are_tracked_for_dedup():
    bot, _ = make_bot()

    async def body():
        await _drive(
            bot,
            [
                {"type": "YOU_ARE", "id": "me"},
                {"type": "TURN_START", "drawerId": "other", "round": 1, "totalRounds": 1},
                {"type": "WORD_SELECTED", "maskedWord": "___", "drawSeconds": 80},
                {"type": "CHAT_MESSAGE", "kind": "normal", "fromId": "someone", "fromName": "Bob", "text": "dog", "color": "#fff"},
            ],
        )
        assert "dog" in bot._others_wrong_guesses
        bot._cancel_turn_tasks()

    asyncio.run(body())
