from __future__ import annotations
from typing import Dict
from app.core.contracts import VerticalAdapter

_REGISTRY: Dict[str, VerticalAdapter] = {}

def register(adapter: VerticalAdapter) -> None:
    vid = adapter.vertical_id
    if not vid:
        raise ValueError("vertical_id required")
    if vid in _REGISTRY:
        raise ValueError(f"Vertical already registered: {vid}")
    _REGISTRY[vid] = adapter

def get(vertical_id: str) -> VerticalAdapter:
    try:
        return _REGISTRY[vertical_id]
    except KeyError:
        raise KeyError(f"Unknown vertical: {vertical_id}. Available: {list(_REGISTRY.keys())}")
