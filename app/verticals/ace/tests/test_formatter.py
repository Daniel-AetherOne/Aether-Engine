from app.verticals.ace.explain.formatter import (
    format_steps_newlines,
    format_steps_bullets_text,
)


def test_formatters():
    steps = ["A", "B"]
    assert format_steps_newlines(steps) == "A\nB"
    assert format_steps_bullets_text(steps).splitlines() == ["• A", "• B"]
