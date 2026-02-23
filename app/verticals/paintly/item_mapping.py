# app/verticals/paintly/item_mapping.py
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
RISK_LABELS: dict[str, str] = {"low": "Low", "medium": "Medium", "high": "High"}


# --- Unit conversions ---
SQFT_TO_M2 = 0.092903
FT_TO_M = 0.3048


@dataclass(frozen=True)
class EstimateItem:
    label: str
    quantity: float
    unit: str  # "m²" | "m" | "rooms" | "each" (fallback)

    # Optional / may be missing if your pricing engine doesn't output it
    unit_price_eur: Decimal | None

    labor_eur: Decimal | None
    materials_eur: Decimal | None
    total_eur: Decimal | None

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
    Canonical units for Paintly EU:
      - "m²" (primary)
      - "m" (for trim/fence linear measures)
      - "rooms"
      - "each"
    Backward compat:
      - sqft -> m²
      - linear ft -> m
    """

    st = _norm_surface_type(surface)

    # ---- 1) Area in square meters (primary) ----
    for k in ("square_meters", "area_m2", "m2", "area_meters", "area_sqm", "sqm"):
        v = _to_float(surface.get(k))
        if v is not None and v > 0:
            return v, "m²"

    # Some vision outputs use generic "area" but may already be m² in EU mode.
    # If you still have US mode producers, they might be sqft—so we only trust "area"
    # if an explicit flag exists.
    v = _to_float(surface.get("area"))
    area_unit = str(surface.get("area_unit") or "").lower().strip()
    if v is not None and v > 0 and area_unit in {"m2", "sqm", "m²"}:
        return v, "m²"

    # ---- 1b) Backward compat: area in square feet -> convert to m² ----
    for k in ("sqft", "area_sqft", "square_feet", "sq_feet"):
        ft2 = _to_float(surface.get(k))
        if ft2 is not None and ft2 > 0:
            return ft2 * SQFT_TO_M2, "m²"

    # If generic "area" but marked as sqft
    if v is not None and v > 0 and area_unit in {"sqft", "ft2", "ft²"}:
        return v * SQFT_TO_M2, "m²"

    # ---- 2) Linear meters ----
    for k in ("linear_m", "linear_meters", "meters", "length_m", "length_meters", "lm"):
        m = _to_float(surface.get(k))
        if m is not None and m > 0:
            return m, "m"

    # Backward compat: linear feet -> meters
    for k in ("linear_ft", "linear_feet", "lf", "length_ft", "length_feet"):
        ft = _to_float(surface.get(k))
        if ft is not None and ft > 0:
            return ft * FT_TO_M, "m"

    # Perimeter fallback for trim/fence
    if _is_trim_like(st):
        m = _to_float(surface.get("perimeter_m") or surface.get("perimeter_meters"))
        if m is not None and m > 0:
            return m, "m"
        ft = _to_float(surface.get("perimeter_ft") or surface.get("perimeter_feet"))
        if ft is not None and ft > 0:
            return ft * FT_TO_M, "m"

    # ---- 3) Rooms / counts ----
    v = _to_float(surface.get("rooms") or surface.get("room_count"))
    if v is not None and v > 0:
        return v, "rooms"

    count = _to_float(surface.get("count"))
    if count is not None and count > 0:
        if _is_door_like(st):
            return count, "each"
        return count, "rooms"

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
    surfaces: vision output list (surface dict must contain surface_type and an area/length/count signal)
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

        # Prefer EUR keys; fallback to legacy USD keys (migration safety)
        labor = _to_decimal(
            p.get("labor_eur") if p.get("labor_eur") is not None else p.get("labor")
        )
        if labor is None:
            labor = _to_decimal(p.get("labor_usd"))

        materials = _to_decimal(
            p.get("materials_eur")
            if p.get("materials_eur") is not None
            else p.get("materials")
        )
        if materials is None:
            materials = _to_decimal(p.get("materials_usd"))

        total = _to_decimal(
            p.get("total_eur") if p.get("total_eur") is not None else p.get("total")
        )
        if total is None:
            total = _to_decimal(p.get("total_usd"))

        if not pricing_ready:
            total = None

        unit_price = _to_decimal(
            p.get("unit_price_eur")
            if p.get("unit_price_eur") is not None
            else p.get("unit_price")
        )
        if unit_price is None:
            unit_price = _to_decimal(p.get("unit_price_usd"))

        item = EstimateItem(
            label=_label_from(_norm_surface_type(s)),
            quantity=qty,
            unit=unit,
            unit_price_eur=unit_price,
            labor_eur=labor,
            materials_eur=materials,
            total_eur=total,
            prep_level=_prep_label(s.get("prep_level")),
            access_risk=_risk_label(s.get("access_risk")),
            confidence=float(s.get("confidence", 0.0) or 0.0),
            pricing_ready=pricing_ready,
            surface_id=surface_id,
        )
        items.append(item)

    return items
