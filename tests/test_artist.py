import asyncio

from ai_player.artist import FallbackShapeArtist, parse_stroke_json


def test_parse_stroke_json_happy_path():
    text = '{"strokes": [[[0.1, 0.2], [0.3, 0.4]], [[0.5, 0.5], [0.6, 0.6], [0.7, 0.7]]]}'
    strokes = parse_stroke_json(text)
    assert len(strokes) == 2
    assert strokes[0] == [(0.1, 0.2), (0.3, 0.4)]
    assert len(strokes[1]) == 3


def test_parse_stroke_json_strips_markdown_fences():
    text = '```json\n{"strokes": [[[0.0, 0.0], [1.0, 1.0]]]}\n```'
    strokes = parse_stroke_json(text)
    assert strokes == [[(0.0, 0.0), (1.0, 1.0)]]


def test_parse_stroke_json_strips_surrounding_prose():
    text = 'Sure, here is the sketch:\n{"strokes": [[[0.0, 0.0], [0.5, 0.5]]]}\nHope that helps!'
    strokes = parse_stroke_json(text)
    assert strokes == [[(0.0, 0.0), (0.5, 0.5)]]


def test_parse_stroke_json_clamps_out_of_range_coordinates():
    text = '{"strokes": [[[-1, 2], [0.5, 0.5]]]}'
    strokes = parse_stroke_json(text)
    assert strokes[0][0] == (0.0, 1.0)


def test_parse_stroke_json_drops_degenerate_single_point_strokes():
    text = '{"strokes": [[[0.1, 0.1]], [[0.2, 0.2], [0.3, 0.3]]]}'
    strokes = parse_stroke_json(text)
    assert len(strokes) == 1


def test_parse_stroke_json_returns_empty_for_garbage():
    assert parse_stroke_json("not json at all") == []
    assert parse_stroke_json("") == []
    assert parse_stroke_json('{"nope": true}') == []


def test_fallback_artist_always_returns_usable_strokes():
    artist = FallbackShapeArtist()
    strokes = asyncio.run(artist.plan_strokes("anything"))
    assert len(strokes) > 0
    for stroke in strokes:
        assert len(stroke) >= 2
        for (x, y) in stroke:
            assert 0.0 <= x <= 1.0
            assert 0.0 <= y <= 1.0


def test_fallback_artist_pick_word_returns_one_of_the_options():
    artist = FallbackShapeArtist()
    options = ["cat", "dog", "sun"]
    picked = asyncio.run(artist.pick_word(options))
    assert picked in options
