# app/verticals/painters_us/vision_aggregate_us.py
from __future__ import annotations

from typing import Any, Dict, List


def aggregate_images_to_surfaces(
    image_predictions: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    MVP heuristic aggregation:
    - Treat the job as 1 main surface (interior_wall) for now
    - confidence = avg substrate_confidence
    - pricing_ready = confidence >= 0.7 and we have at least 3 images
    - sqft fallback = 200
    """
    if not image_predictions:
        return {"surfaces": []}

    confs = [
        float(p.get("substrate_confidence", 0.0) or 0.0) for p in image_predictions
    ]
    avg_conf = sum(confs) / max(len(confs), 1)

    pricing_ready = (avg_conf >= 0.70) and (len(image_predictions) >= 3)

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
