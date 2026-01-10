# app/verticals/painters_us/item_mapping.py
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


SURFACE_LABELS: dict[str, str] = {
    # interior
    "interior_wall": "Interior wall painting",
    "interior_ceiling": "Ceiling painting",
    "interior_trim": "Interior trim painting",
    "interior_door": "Interior door painting",
    # exterior
    "exterior_siding": "Exterior siding painting",
    "exterior_trim": "Exterior trim painting",
    "exterior_door": "Exterior door painting",
    "fence": "Fence / deck painting",
    "garage_door": "Garage door painting",
    # fallback
    "unknown": "Painting work",
}

PREP_LABELS: dict[str, str] = {
    "light": "Light",
    "standard": "Standard",
    "heavy": "Heavy",
}

RISK_LABELS: dict[str, str] = {
    "low": "Low",
    "medium": "Medium",
    "high": "High",
}


@dataclass(frozen=True)
class EstimateItem:
    label: str
    quantity: float
    unit: str  # "sqft" | "linear ft" | "rooms" | "each" (fallback)

    # Optional / may be missing if your pricing engine doesn't output it
    unit_price_usd: Decimal | None

    labor_usd: Decimal | None
    materials_usd: Decimal | None
    total_usd: Decimal | None

    prep_level: str
    access_risk: str
    confidence: float
    pricing_ready: bool

    # Keep ids internal (do not render)
    surface_id: str | None = None


def _to_decimal(x: Any) -> Decimal | None:
    if x is None:
        return None
    return x if isinstance(x, Decimal) else Decimal(str(x))


def _label_from(surface_type: str) -> str:
    if not surface_type:
        return SURFACE_LABELS["unknown"]
    return SURFACE_LABELS.get(surface_type, SURFACE_LABELS["unknown"])


def _norm_surface_type(surface: dict[str, Any]) -> str:
    st = str(surface.get("surface_type") or surface.get("type") or "").strip()
    return st or "unknown"


def _is_trim_like(surface_type: str) -> bool:
    return "trim" in surface_type or surface_type in {"fence"}


def _is_door_like(surface_type: str) -> bool:
    return "door" in surface_type


def _to_float(x: Any) -> float | None:
    if x is None:
        return None
    try:
        return float(x)
    except Exception:
        return None


def _pick_quantity(surface: dict[str, Any]) -> tuple[float, str]:
    """
    Canonical units for US painters:
      - "sqft"
      - "linear ft"
      - "rooms"
    Fallback:
      - "each" (doors, etc.) if no better signal exists.
    """

    st = _norm_surface_type(surface)

    # ---- 1) Area in square feet ----
    for k in ("sqft", "area_sqft", "square_feet", "sq_feet"):
        v = _to_float(surface.get(k))
        if v is not None and v > 0:
            return v, "sqft"

    # Some vision outputs use generic "area" but already in sqft
    v = _to_float(surface.get("area"))
    if v is not None and v > 0:
        return v, "sqft"

    # ---- 2) Linear feet ----
    for k in ("linear_ft", "linear_feet", "lf", "length_ft", "length_feet"):
        v = _to_float(surface.get(k))
        if v is not None and v > 0:
            return v, "linear ft"

    # If trim/fence-like and we only have perimeter-ish info, treat as linear ft
    # (This only works if your vision output provides it.)
    if _is_trim_like(st):
        v = _to_float(surface.get("perimeter_ft") or surface.get("perimeter_feet"))
        if v is not None and v > 0:
            return v, "linear ft"

    # ---- 3) Rooms / counts ----
    # Explicit rooms field
    v = _to_float(surface.get("rooms") or surface.get("room_count"))
    if v is not None and v > 0:
        return v, "rooms"

    # Generic count: decide based on surface_type
    count = _to_float(surface.get("count"))
    if count is not None and count > 0:
        # Doors are often "each" unless you provide linear ft or sqft
        if _is_door_like(st):
            return count, "each"
        # Otherwise treat counts as rooms (common intake/vision abstraction)
        return count, "rooms"

    # ---- last resort ----
    return 0.0, "rooms"


def _prep_label(prep: str | None) -> str:
    if not prep:
        return "Standard"
    return PREP_LABELS.get(prep.lower(), prep.title())


def _risk_label(risk: str | None) -> str:
    if not risk:
        return "Low"
    return RISK_LABELS.get(risk.lower(), risk.title())


def map_surfaces_to_items(
    *,
    surfaces: list[dict[str, Any]],
    pricing: dict[str, Any],
) -> list[EstimateItem]:
    """
    surfaces: vision output list (each surface dict must contain surface_type, sqft/linear_ft/count, etc.)
    pricing: pricing output dict; ideally contains per-surface breakdown keyed by surface_id.
    """
    pricing_items = pricing.get("items", {}) or {}
    items: list[EstimateItem] = []

    for i, s in enumerate(surfaces):
        surface_id = s.get("surface_id") or s.get("id") or str(i)

        qty, unit = _pick_quantity(s)

        # Surface-level override if present, otherwise assume pricing is ready
        pricing_ready = bool(s.get("pricing_ready", True))

        p = pricing_items.get(surface_id, {}) if isinstance(pricing_items, dict) else {}

        labor = _to_decimal(p.get("labor_usd"))
        materials = _to_decimal(p.get("materials_usd"))
        total = _to_decimal(p.get("total_usd")) if pricing_ready else None
        unit_price = _to_decimal(p.get("unit_price_usd"))  # optional

        item = EstimateItem(
            label=_label_from(_norm_surface_type(s)),
            quantity=qty,
            unit=unit,
            unit_price_usd=unit_price,
            labor_usd=labor,
            materials_usd=materials,
            total_usd=total,
            prep_level=_prep_label(s.get("prep_level")),
            access_risk=_risk_label(s.get("access_risk")),
            confidence=float(s.get("confidence", 0.0) or 0.0),
            pricing_ready=pricing_ready,
            surface_id=surface_id,
        )
        items.append(item)

    return items
