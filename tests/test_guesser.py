import asyncio
import random

from ai_player.guesser import HeuristicGuesser, _clean_guess, _non_space_length


def test_heuristic_guesser_respects_mask_length():
    # The real server masks a hidden word as one underscore per letter, no
    # separators (see GameRoom.maskWord) — "___" for a 3-letter word.
    guesser = HeuristicGuesser(vocab=["cat", "house", "sun"], rng=random.Random(0))
    guess = asyncio.run(guesser.guess(b"", "___", []))
    assert guess in ("cat", "sun")


def test_non_space_length_counts_underscores_not_spaces():
    assert _non_space_length("___") == 3
    assert _non_space_length("a__ ___") == 6


def test_heuristic_guesser_respects_revealed_letters():
    guesser = HeuristicGuesser(vocab=["cat", "car", "cup"], rng=random.Random(0))
    guess = asyncio.run(guesser.guess(b"", "ca_", []))
    assert guess in ("cat", "car")


def test_heuristic_guesser_avoids_already_tried():
    guesser = HeuristicGuesser(vocab=["cat", "car"], rng=random.Random(0))
    guess = asyncio.run(guesser.guess(b"", "ca_", ["car"]))
    assert guess == "cat"


def test_heuristic_guesser_returns_none_when_exhausted():
    guesser = HeuristicGuesser(vocab=["cat"], rng=random.Random(0))
    guess = asyncio.run(guesser.guess(b"", "___", ["cat"]))
    assert guess is None


def test_clean_guess_strips_punctuation_and_extra_prose():
    assert _clean_guess("A cat.") == "A cat"
    assert _clean_guess('"dog"') == "dog"


def test_clean_guess_handles_pass():
    assert _clean_guess("PASS") is None
    assert _clean_guess("  pass  ") is None


def test_clean_guess_handles_empty():
    assert _clean_guess("") is None
    assert _clean_guess("   ") is None
