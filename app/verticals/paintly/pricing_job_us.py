# app/verticals/painters_us/pricing_job_us.py
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from app.verticals.paintly.pricing_engine_us import price_from_vision


def _surface_id(surface: Dict[str, Any], idx: int) -> str:
    return str(surface.get("surface_id") or surface.get("id") or f"s{idx+1}")


def price_job_from_vision(vision_output: Dict[str, Any]) -> Dict[str, Any]:
    """
    Aggregate per-surface pricing into a job-level pricing output.

    Returns a dict shaped to work with:
      - item_mapping.map_surfaces_to_items(surfaces, pricing)
      - render_estimate.render_us_estimate_html(...)

    Expected vision_output shape:
      {"surfaces": [ {surface_type, sqft/count, prep_level, access_risk, estimated_complexity, confidence, pricing_ready, ...}, ... ]}
    """
    surfaces: List[Dict[str, Any]] = list(vision_output.get("surfaces") or [])

    items: Dict[str, Any] = {}

    # Totals (only if pricing_ready stays True)
    labor_total = 0.0
    materials_total = 0.0
    total_total = 0.0

    # Range aggregation (if any surface is needs_review)
    range_low = 0.0
    range_high = 0.0
    any_needs_review = False

    for idx, s in enumerate(surfaces):
        sid = _surface_id(s, idx)
        r = price_from_vision(s)

        # Keep per-surface item in a map for the template/mapping layer
        # Normalize into "items" dict:
        # - when priced: labor/materials/total/unit_price possibly in r["line_items"][0]
        # - when needs_review: store low/high in estimate_range
        per_item: Dict[str, Any] = {
            "status": r.get("status"),
            "currency": r.get("currency", "EUR"),
        }

        if r.get("status") == "needs_review" or r.get("needs_review") is True:
            any_needs_review = True
            est = r.get("estimate_range") or {}
            low = float(est.get("low_eur") or 0.0)
            high = float(est.get("high_eur") or 0.0)
            range_low += low
            range_high += high

            # For needs-review items: we do not provide a hard total
            per_item.update(
                {
                    "labor_eur": None,
                    "materials_eur": None,
                    "total_eur": None,
                    "estimate_range": {"low_eur": low, "high_eur": high},
                }
            )
        elif r.get("status") == "priced_with_margin":
            # Totals for job
            labor = float(r.get("labor_eur") or 0.0)
            materials = float(r.get("materials_eur") or 0.0)
            total = float(r.get("total_eur") or 0.0)

            labor_total += labor
            materials_total += materials
            total_total += total

            # Try to capture unit_price_eur from line_items[0] if present
            line_items = r.get("line_items") or []
            unit_price = None
            if line_items and isinstance(line_items, list):
                unit_price = line_items[0].get("unit_price_eur")

            per_item.update(
                {
                    "unit_price_eur": unit_price,
                    "labor_eur": round(labor, 2),
                    "materials_eur": round(materials, 2),
                    "total_eur": round(total, 2),
                }
            )
        else:
            # pricing_blocked / unsupported_surface_type / etc.
            any_needs_review = True
            # We do NOT hard fail for MVP; we just force needs review behavior.
            per_item.update(
                {
                    "labor_eur": None,
                    "materials_eur": None,
                    "total_eur": None,
                    "estimate_range": {"low_eur": 0.0, "high_eur": 0.0},
                    "reason": r.get("reason", "pricing_blocked"),
                }
            )

        items[sid] = per_item

    # Job-level shape
    if any_needs_review:
        return {
            "currency": "EUR",
            "pricing_ready": False,
            "needs_review": True,
            "labor_eur": None,
            "materials_eur": None,
            "total_eur": None,
            "estimate_range": {
                "low_eur": round(range_low, 2),
                "high_eur": round(range_high, 2),
            },
            "items": items,
        }

    return {
        "currency": "EUR",
        "pricing_ready": True,
        "needs_review": False,
        "labor_eur": round(labor_total, 2),
        "materials_eur": round(materials_total, 2),
        "total_eur": round(total_total, 2),
        "items": items,
    }
