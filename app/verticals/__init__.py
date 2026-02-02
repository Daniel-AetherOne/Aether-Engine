from __future__ import annotations

from app.verticals.registry import register
from app.verticals.painters_us.adapter import PaintersUSAdapter


def register_verticals(app=None) -> None:
    # Paintly MVP
    register(PaintersUSAdapter())
