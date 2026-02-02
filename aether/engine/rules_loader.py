from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict


def load_json(path: str) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Rules file not found: {path}")
    return json.loads(p.read_text(encoding="utf-8"))
