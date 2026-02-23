# app/verticals/painters_us/vision_aggregate_us.py
from __future__ import annotations

import json
from typing import Any, Dict, List


def _ensure_obj(x: Any) -> Any:
    """Parse JSON strings into python objects when possible."""
    if isinstance(x, str):
        try:
            return json.loads(x)
        except Exception:
            return x
    return x


def _ensure_list_of_dicts(x: Any) -> List[Dict[str, Any]]:
    """
    Accepts:
      - list[dict]
      - list[str] where each str is JSON dict
      - str containing JSON list/dict
    Returns list[dict], dropping invalid items.
    """
    x = _ensure_obj(x)

    if x is None:
        return []

    if isinstance(x, dict):
        return [x]

    if isinstance(x, list):
        out: List[Dict[str, Any]] = []
        for item in x:
            item = _ensure_obj(item)
            if isinstance(item, dict):
                out.append(item)
        return out

    return []


def aggregate_images_to_surfaces(image_predictions: Any) -> Dict[str, Any]:
    """
    MVP heuristic aggregation:
    - Treat the job as 1 main surface (interior_wall) for now
    - confidence = avg substrate_confidence
    - pricing_ready = confidence >= 0.7 and we have at least 3 images
    - sqft fallback = 200

    Robust to messy vision output (strings / json strings).
    """
    preds = _ensure_list_of_dicts(image_predictions)
    if not preds:
        return {"surfaces": []}

    confs: List[float] = []
    for p in preds:
        try:
            confs.append(float(p.get("substrate_confidence", 0.0) or 0.0))
        except Exception:
            confs.append(0.0)

    avg_conf = sum(confs) / max(len(confs), 1)
    pricing_ready = (avg_conf >= 0.70) and (len(preds) >= 3)

    surface = {
        "surface_id": "s1",
        "surface_type": "interior_wall",
        "sqft": 200,
        "prep_level": "standard",
        "access_risk": "low",
        "estimated_complexity": 1.1,
        "confidence": round(avg_conf, 3),
        "pricing_ready": bool(pricing_ready),
    }

    return {"surfaces": [surface]}
