# app/services/metrics.py
from __future__ import annotations

from collections import defaultdict
from threading import Lock
from typing import Dict

_lock = Lock()
_counters: defaultdict[str, int] = defaultdict(int)


def inc(name: str, value: int = 1) -> None:
    if not name:
        return
    v = int(value or 0)
    with _lock:
        _counters[name] += v
        # TEMP debug (haal later weg)
        print("METRIC", name, _counters[name])


def snapshot() -> Dict[str, int]:
    with _lock:
        return dict(_counters)
