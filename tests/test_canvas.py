from ai_player.canvas import VirtualCanvas


def test_blank_canvas_has_no_strokes():
    canvas = VirtualCanvas(100, 100)
    assert canvas.is_blank()
    assert canvas.stroke_count == 0


def test_draw_stroke_marks_canvas_dirty():
    canvas = VirtualCanvas(100, 100)
    canvas.apply_event({"type": "DRAW", "x": 0.1, "y": 0.1, "color": "#000000", "brushSize": 4, "startStroke": True})
    canvas.apply_event({"type": "DRAW", "x": 0.2, "y": 0.2, "color": "#000000", "brushSize": 4, "startStroke": False})
    assert not canvas.is_blank()
    assert canvas.stroke_count == 2


def test_line_event_draws_without_stroke_state():
    canvas = VirtualCanvas(100, 100)
    canvas.apply_event({"type": "LINE", "x": 0, "y": 0, "x2": 0.5, "y2": 0.5, "color": "#000000", "brushSize": 4})
    assert not canvas.is_blank()


def test_clear_resets_canvas():
    canvas = VirtualCanvas(100, 100)
    canvas.apply_event({"type": "DRAW", "x": 0.1, "y": 0.1, "color": "#000000", "brushSize": 4, "startStroke": True})
    canvas.apply_event({"type": "CLEAR"})
    assert canvas.is_blank()
    assert canvas.stroke_count == 0


def test_out_of_bounds_coordinates_are_clamped_not_crashing():
    canvas = VirtualCanvas(100, 100)
    canvas.apply_event({"type": "DRAW", "x": -0.5, "y": 99, "color": "#000000", "brushSize": 4, "startStroke": True})
    canvas.apply_event({"type": "DRAW", "x": 50, "y": -50, "color": "#000000", "brushSize": 4, "startStroke": False})
    assert not canvas.is_blank()


def test_png_bytes_round_trip():
    canvas = VirtualCanvas(50, 40)
    data = canvas.png_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic bytes
