"""End-to-end test against a scripted mock PictionaryServer over a real
WebSocket, exercising client.py + bot.py together (not just bot._handle()).

We can't run the actual Java PictionaryServer in this environment, so this
mock replays the exact message shapes documented in Doodle-Room's README —
see the docstring in ai_player/client.py for where those come from.
"""

import asyncio
import json
import random

import websockets

from ai_player.artist import FallbackShapeArtist
from ai_player.bot import PictionaryBot
from ai_player.config import BotConfig
from ai_player.guesser import HeuristicGuesser


async def _mock_server_handler(ws, received: list[dict]):
    await ws.recv()  # CREATE_ROOM from the bot — ignored, content doesn't matter here

    async def send(payload: dict) -> None:
        await ws.send(json.dumps(payload))

    await send({"type": "YOU_ARE", "id": "bot1"})
    await send(
        {
            "type": "ROOM_STATE",
            "roomCode": "TEST1",
            "phase": "LOBBY",
            "players": [{"id": "bot1", "name": "Bot", "color": "#fff", "isHost": True, "score": 0}],
            "config": {"rounds": 1, "drawSeconds": 10, "categories": ["easy"], "customWords": []},
            "round": 1,
            "totalRounds": 1,
        }
    )
    await send({"type": "GAME_STARTED"})
    await send({"type": "TURN_START", "drawerId": "other", "drawerName": "Alice", "round": 1, "totalRounds": 1})
    await send({"type": "WORD_SELECTED", "maskedWord": "___", "drawSeconds": 10})
    await send({"type": "DRAW", "x": 10, "y": 10, "color": "#000", "brushSize": 4, "startStroke": True, "userId": "other"})
    await send({"type": "DRAW", "x": 20, "y": 20, "color": "#000", "brushSize": 4, "startStroke": False, "userId": "other"})

    guess_raw = await asyncio.wait_for(ws.recv(), timeout=5)
    received.append(json.loads(guess_raw))

    await send({"type": "CHAT_MESSAGE", "kind": "correct", "fromId": "bot1", "fromName": "Bot", "points": 100})
    await send({"type": "TURN_END", "reason": "all_guessed", "word": "cat"})
    await send({"type": "GAME_OVER", "scores": [{"id": "bot1", "name": "Bot", "score": 100}]})
    await ws.close()


def test_bot_plays_a_full_scripted_turn_over_a_real_websocket():
    received: list[dict] = []

    async def body():
        server = await websockets.serve(lambda ws: _mock_server_handler(ws, received), "localhost", 0)
        port = server.sockets[0].getsockname()[1]
        try:
            config = BotConfig(
                server_url=f"ws://localhost:{port}",
                create_room=True,
                min_seconds_before_first_guess=0.0,
                guess_cooldown_seconds=0.01,
                max_guesses_per_turn=3,
            )
            bot = PictionaryBot(config, HeuristicGuesser(rng=random.Random(0)), FallbackShapeArtist())
            await asyncio.wait_for(bot.run(), timeout=8)
        finally:
            server.close()
            await server.wait_closed()

    asyncio.run(body())

    assert len(received) == 1
    assert received[0]["type"] == "CHAT_GUESS"
    assert isinstance(received[0]["text"], str) and received[0]["text"]
