from __future__ import annotations

from app.verticals.registry import register
from app.verticals.paintly.adapter import PaintlyAdapter


def register_verticals(app=None) -> None:
    # Paintly EU-first vertical
    register(
        PaintlyAdapter(),
        aliases=["painters_us"],   # backward compatibility
    )