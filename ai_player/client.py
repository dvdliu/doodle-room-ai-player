"""Thin async WebSocket transport. Connects, sends JSON, iterates parsed messages.

Deliberately dumb. No game knowledge lives here. See `bot.py` for that.
"""

from __future__ import annotations

import json
import logging
from typing import AsyncIterator

import websockets

log = logging.getLogger("ai_player.client")


class PictionaryConnection:
    def __init__(self, server_url: str):
        self.server_url = server_url
        self._ws: websockets.WebSocketClientProtocol | None = None

    async def __aenter__(self) -> "PictionaryConnection":
        self._ws = await websockets.connect(self.server_url, ping_interval=20, ping_timeout=20)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._ws is not None:
            await self._ws.close()

    async def send(self, payload: dict) -> None:
        assert self._ws is not None, "not connected"
        raw = json.dumps(payload)
        log.debug("-> %s", raw)
        await self._ws.send(raw)

    async def messages(self) -> AsyncIterator[dict]:
        assert self._ws is not None, "not connected"
        async for raw in self._ws:
            log.debug("<- %s", raw)
            try:
                yield json.loads(raw)
            except json.JSONDecodeError:
                log.warning("Dropped malformed message: %r", raw)
