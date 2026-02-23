from __future__ import annotations
from typing import Dict
from app.core.contracts import VerticalAdapter

_REGISTRY: Dict[str, VerticalAdapter] = {}
_ALIASES: Dict[str, str] = {}  # alias -> canonical id


def register(adapter: VerticalAdapter, aliases: list[str] | None = None) -> None:
    vid = adapter.vertical_id
    if not vid:
        raise ValueError("vertical_id required")

    if vid in _REGISTRY:
        raise ValueError(f"Vertical already registered: {vid}")

    _REGISTRY[vid] = adapter

    # register aliases
    if aliases:
        for alias in aliases:
            _ALIASES[alias] = vid


def get(vertical_id: str) -> VerticalAdapter:
    # resolve alias
    vertical_id = _ALIASES.get(vertical_id, vertical_id)

    try:
        return _REGISTRY[vertical_id]
    except KeyError:
        raise KeyError(
            f"Unknown vertical: {vertical_id}. "
            f"Available: {list(_REGISTRY.keys())}, aliases: {list(_ALIASES.keys())}"
        )
