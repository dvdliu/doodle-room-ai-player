"""Command-line entry point. Run it with `python -m ai_player ...`"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

from .artist import Artist, ClaudeStrokeArtist, FallbackShapeArtist
from .bot import PictionaryBot
from .config import BotConfig
from .guesser import ClaudeVisionGuesser, Guesser, HeuristicGuesser


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ai_player",
        description="An AI player for Doodle Room's Pictionary game.",
    )
    p.add_argument("--server", default="ws://localhost:8081", help="PictionaryServer WebSocket URL")
    p.add_argument("--name", default="Claude", help="Display name the bot joins as")

    room = p.add_mutually_exclusive_group(required=True)
    room.add_argument("--room", metavar="CODE", help="Room code to join")
    room.add_argument("--create", action="store_true", help="Create a new room instead of joining one")

    p.add_argument(
        "--offline",
        action="store_true",
        help="Never call the Anthropic API, use the built-in heuristic guesser/artist instead",
    )
    p.add_argument("--model", default="claude-sonnet-5", help="Anthropic model to use")
    p.add_argument(
        "--anthropic-key",
        default=None,
        help="Anthropic API key (defaults to the ANTHROPIC_API_KEY env var)",
    )
    p.add_argument("--guess-cooldown", type=float, default=4.0, help="Seconds between guess attempts")
    p.add_argument("-v", "--verbose", action="store_true", help="Debug logging, including raw WS traffic")
    return p


def build_guesser_and_artist(config: BotConfig) -> tuple[Guesser, Artist]:
    if config.offline:
        return HeuristicGuesser(), FallbackShapeArtist()

    try:
        from anthropic import AsyncAnthropic
    except ImportError:
        print(
            "The 'anthropic' package isn't installed. Run `pip install -r requirements.txt`, "
            "or pass --offline to use the heuristic guesser/artist instead.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    api_key = config.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print(
            "No Anthropic API key found. Set ANTHROPIC_API_KEY, pass --anthropic-key, "
            "or pass --offline to run without one.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    client = AsyncAnthropic(api_key=api_key)
    return ClaudeVisionGuesser(client, model=config.model), ClaudeStrokeArtist(client, model=config.model)


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    config = BotConfig(
        server_url=args.server,
        name=args.name,
        room_code=args.room,
        create_room=args.create,
        offline=args.offline,
        anthropic_api_key=args.anthropic_key,
        model=args.model,
        guess_cooldown_seconds=args.guess_cooldown,
    )

    guesser, artist = build_guesser_and_artist(config)
    bot = PictionaryBot(config, guesser, artist)

    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        pass
    except OSError as e:
        print(
            f"Couldn't reach {config.server_url}. Is the PictionaryServer running there? "
            f"(./start-pictionary-server.sh in Doodle-Room)\n{e}",
            file=sys.stderr,
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
