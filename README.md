# Doodle Room AI Player

An AI player for [Doodle Room](../Doodle-Room)'s Pictionary game mode. It connects to a
running `PictionaryServer` as a regular WebSocket player — no changes to Doodle Room
itself — and plays both roles:

- **Guessing**: replays the drawer's strokes onto a virtual canvas, periodically shows a
  snapshot to Claude (vision), and sends its best guess as a chat message, same as a
  human typing into the guess box.
- **Drawing**: when it's picked as the drawer, asks Claude to *design* a simple stroke-by-stroke
  sketch of the word as JSON, then executes that plan as real `DRAW` events, paced to
  fit inside the turn's time limit.

Both roles are two applications of the same idea — one Claude call turns pixels into a
word, the other turns a word into pixels — over a state machine that tracks turns,
scoring, and pacing so the bot behaves like a (reasonably) well-mannered player.

## Setup

Requires Python 3.9+ and a running Doodle Room `PictionaryServer` (see
[Doodle-Room/README.md](../Doodle-Room/README.md) — `./start-pictionary-server.sh`, default
`ws://localhost:8081`).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export ANTHROPIC_API_KEY=sk-ant-...   # skip this if you're only using --offline
```

## Usage

Create a new room and have the bot host it, then join with `pictionary.html` in a
browser using the room code it prints:

```bash
python -m ai_player --create --name "Claude"
```

Or join a room a human already created:

```bash
python -m ai_player --room ABCDE --name "Claude"
```

Try it without an API key (a heuristic guesser + a placeholder sketch — good for
checking the plumbing works, not for an actual demo):

```bash
python -m ai_player --create --offline
```

Run `python -m ai_player --help` for the rest of the flags (model, guess pacing, a
custom server URL, verbose/raw-traffic logging).

## How it works

```
pictionary.html (human) ──┐
                           ├──▶ PictionaryServer (ws://localhost:8081)
ai_player (this project) ──┘         (unmodified — the bot is just another client)
```

| File | Responsibility |
| --- | --- |
| `ai_player/client.py` | Dumb WebSocket transport — connect, send JSON, iterate parsed messages |
| `ai_player/canvas.py` | Replays `DRAW`/`LINE`/`CLEAR` events onto a Pillow image, matching `pictionary.html`'s rendering closely enough to snapshot for a vision model |
| `ai_player/guesser.py` | `Guesser` strategy: `ClaudeVisionGuesser` (real) and `HeuristicGuesser` (offline fallback — filters a small wordlist by mask length/revealed letters) |
| `ai_player/artist.py` | `Artist` strategy: `ClaudeStrokeArtist` asks Claude for a JSON stroke plan `{"strokes": [[[x,y],...], ...]}`; `FallbackShapeArtist` guarantees a turn never stalls if planning fails |
| `ai_player/bot.py` | The state machine — tracks phase/turn/score from server events, runs a background guess loop while someone else draws and a background draw loop on its own turn |
| `ai_player/cli.py` | `python -m ai_player ...` |

The message protocol itself (types, fields, phases) isn't reinvented here — it's
implemented exactly as documented in
[Doodle-Room/README.md § Message protocol](../Doodle-Room/README.md#message-protocol),
against the source in `com.pictionary.*`.

### Guessing loop

On `WORD_SELECTED` (and not the drawer), the bot starts a background loop: wait a
couple seconds for something to appear, snapshot the canvas, ask Claude for a guess,
send it as `CHAT_GUESS`, then wait out a cooldown before trying again — repeating until
it guesses correctly, the turn ends, or it hits a max-attempts cap. A `LETTER_REVEAL`
wakes the loop early to retry sooner with the new information, and it's fed a running
list of other players' wrong guesses so it doesn't repeat them.

### Drawing loop

On `WORD_OPTIONS` (only sent to the drawer), the bot picks the shortest of the three
offered words (a cheap proxy for "simplest to sketch clearly in the time given") and
immediately asks Claude to plan the sketch in the background while the server's pick
window elapses. On `WORD_SELECTED` it replays the planned strokes as timed `DRAW`
events, budgeted to finish within roughly 75% of the turn's `drawSeconds`.

## Testing

```bash
pip install -r requirements-dev.txt
python -m pytest
```

No API key or running server needed — `test_canvas.py`/`test_guesser.py`/`test_artist.py`
cover the pure logic (stroke replay, mask-based filtering, stroke-plan JSON parsing),
`test_bot.py` drives the state machine with a fake connection, and
`test_integration.py` runs the bot against a real WebSocket connection to a small
scripted mock server (a full turn: connect → draw → guess → correct → game over) —
so the wire-level plumbing is covered even without the actual Java server available.

## Demos

_Coming soon — a recording of the bot guessing (and drawing) live against a human in
Doodle Room. Requires the JDK/Maven toolchain to actually run `PictionaryServer`, which
this development environment didn't have on hand._
