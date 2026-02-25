from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, Union


# -------------------------
# Helpers
# -------------------------
SQM_TO_SQFT = 10.763910416709722


def complexity_bucket(value: float) -> str:
    if value >= 1.3:
        return "high"
    if value >= 1.1:
        return "medium"
    return "low"


def _load_rules_file(filename: str) -> Dict[str, Any]:
    rules_path = Path(__file__).parent / "rules" / filename
    if not rules_path.exists():
        raise FileNotFoundError(f"Pricing rules not found: {rules_path}")
    return json.loads(rules_path.read_text(encoding="utf-8"))


def load_rules_default() -> Dict[str, Any]:
    """
    Default fallback loader (used if engine does not inject rules).
    Prefer EU/paintly rules as default when you're migrating.
    """
    # Change this default to your EU rules filename
    return _load_rules_file("paintly_price_rules_eu.json")


def load_rules_us() -> Dict[str, Any]:
    return _load_rules_file("pricing_rules_us.json")


def load_rules_eu() -> Dict[str, Any]:
    # rename as you like: paintly_price_rules.json, pricing_rules_nl.json, etc.
    return _load_rules_file("paintly_price_rules_eu.json")


def _pick_rules_from_lead(lead: Any) -> Optional[Dict[str, Any]]:
    """
    Optional: auto-select rules based on lead / tenant metadata.
    If you already inject `rules` from the pipeline, you can ignore this.
    """
    market = None
    locale = None

    # try common shapes without hard dependency
    for attr in ("market", "locale", "region"):
        if hasattr(lead, attr):
            v = getattr(lead, attr)
            if isinstance(v, str) and v:
                if attr == "market":
                    market = v
                if attr == "locale":
                    locale = v

    tenant = getattr(lead, "tenant", None)
    if tenant is not None:
        if market is None and hasattr(tenant, "market"):
            v = getattr(tenant, "market")
            if isinstance(v, str) and v:
                market = v
        if locale is None and hasattr(tenant, "locale"):
            v = getattr(tenant, "locale")
            if isinstance(v, str) and v:
                locale = v

    key = (market or locale or "").lower()
    if not key:
        return None

    # very simple routing
    if "us" in key or "en-us" in key or "usa" in key:
        return load_rules_us()
    if "nl" in key or "eu" in key or "europe" in key or "en-nl" in key:
        return load_rules_eu()

    return None


def _get_area_sqm(vision_surface: Dict[str, Any]) -> float:
    """
    Canonical area for EU: sqm.
    Supports multiple possible keys from your vision/metrics pipeline.
    """
    # direct
    for k in ("area_sqm", "total_area_sqm", "wall_area_sqm", "ceiling_area_sqm", "sqm"):
        v = vision_surface.get(k)
        if v is not None:
            try:
                return float(v or 0)
            except (TypeError, ValueError):
                pass

    # nested common shapes (optional)
    m = (
        vision_surface.get("surface_metrics")
        or vision_surface.get("measurements")
        or {}
    )
    if isinstance(m, dict):
        for k in (
            "area_sqm",
            "total_area_sqm",
            "wall_area_sqm",
            "ceiling_area_sqm",
            "sqm",
        ):
            v = m.get(k)
            if v is not None:
                try:
                    return float(v or 0)
                except (TypeError, ValueError):
                    pass

    return 0.0


def _get_quantity_for_rate(
    rate_cfg: Dict[str, Any], vision_surface: Dict[str, Any]
) -> float:
    """
    Returns the quantity in the unit required by the rate config.
    Supported units: sqm, sqft, per_item, fixed.
    """
    unit = (rate_cfg.get("unit") or "").lower()

    if unit == "sqm":
        return _get_area_sqm(vision_surface)

    if unit == "sqft":
        sqft = vision_surface.get("sqft")
        if sqft is not None:
            try:
                return float(sqft or 0)
            except (TypeError, ValueError):
                return 0.0
        # fallback: convert sqm -> sqft
        return _get_area_sqm(vision_surface) * SQM_TO_SQFT

    if unit in ("per_item", "item", "items"):
        try:
            return float(int(vision_surface.get("count", 1)))
        except (TypeError, ValueError):
            return 1.0

    if unit == "fixed":
        return 1.0

    # Unknown unit => quantity 0
    return 0.0


def _has_pricing_area(rate_cfg: Dict[str, Any], vision_surface: Dict[str, Any]) -> bool:
    unit = (rate_cfg.get("unit") or "").lower()
    if unit in ("sqm", "sqft"):
        return _get_quantity_for_rate(rate_cfg, vision_surface) > 0
    return True


# -------------------------
# Main pricing logic
# -------------------------
def price_from_vision(
    vision_surface: Dict[str, Any],
    rules: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    rules = rules or load_rules_default()

    # -------------------------
    # Gates
    # -------------------------
    gates = rules.get("gates", {})

    # optional: if you want EU migration to not hard-block on pricing_ready,
    # set require_pricing_ready=false in EU rules.
    pricing_ready = bool(vision_surface.get("pricing_ready", False))
    require_pricing_ready = bool(gates.get("require_pricing_ready", False))

    min_conf = float(gates.get("min_confidence", 0.0))
    conf = float(vision_surface.get("confidence", 0.0) or 0.0)
    if conf < min_conf:
        return {
            "status": "pricing_blocked",
            "reason": "LOW_CONFIDENCE",
            "confidence": conf,
        }

    # -------------------------
    # Base rates
    # -------------------------
    base_rates = rules.get("base_rates", {})
    if not base_rates:
        return {
            "status": "no_pricing_defined",
            "reason": "NO_BASE_RATES",
            "total_eur": 0.0,
            "line_items": [],
        }

    surface_type = vision_surface.get("surface_type")
    if surface_type not in base_rates:
        return {
            "status": "pricing_blocked",
            "reason": "UNSUPPORTED_SURFACE_TYPE",
            "surface_type": surface_type,
        }

    rate_cfg = base_rates[surface_type]

    # If pricing_ready is required, allow a range estimate (instead of €0)
    if require_pricing_ready and not pricing_ready:
        rng_cfg = rules.get("estimate_range", {})
        low_factor = float(rng_cfg.get("low_factor", 0.85))
        high_factor = float(rng_cfg.get("high_factor", 1.15))

        # If area exists, we can still compute a meaningful base estimate.
        qty = _get_quantity_for_rate(rate_cfg, vision_surface)
        base_estimate = 0.0

        unit = (rate_cfg.get("unit") or "").lower()
        if unit in ("sqm", "sqft"):
            base_estimate = qty * float(rate_cfg.get("rate_eur", 0.0))
        elif unit in ("per_item", "item", "items"):
            base_estimate = qty * float(rate_cfg.get("rate_eur", 0.0))
        elif unit == "fixed":
            base_estimate = float(rate_cfg.get("base_eur", 0.0))

        low = round(base_estimate * low_factor, 2)
        high = round(base_estimate * high_factor, 2)

        return {
            "status": "needs_review",
            "reason": "PRICING_NOT_READY",
            "currency": rules.get("currency", "EUR"),
            "needs_review": True,
            "total_eur": None,
            "estimate_range": {
                "low_eur": low,
                "high_eur": high,
                "basis": "base_rates_only",
                "factors": {"low": low_factor, "high": high_factor},
            },
            "surface_type": surface_type,
            "confidence": conf,
        }

    # Hard-block if we need area but have none (prevents silent €0)
    if not _has_pricing_area(rate_cfg, vision_surface):
        return {
            "status": "pricing_blocked",
            "reason": "NO_SURFACE_AREA",
            "surface_type": surface_type,
            "confidence": conf,
            "debug": {
                "expected_unit": rate_cfg.get("unit"),
                "available_keys": sorted(list(vision_surface.keys())),
            },
        }

    # -------------------------
    # Compute base total
    # -------------------------
    line_items = []
    base_total = 0.0

    unit = (rate_cfg.get("unit") or "").lower()
    if unit in ("sqm", "sqft"):
        qty = _get_quantity_for_rate(rate_cfg, vision_surface)
        base_total = qty * float(rate_cfg["rate_eur"])
        line_items.append(
            {
                "surface_type": surface_type,
                "quantity": round(qty, 4),
                "unit": unit,
                "unit_price_eur": float(rate_cfg["rate_eur"]),
                "base_total_eur": round(base_total, 2),
            }
        )

    elif unit in ("per_item", "item", "items"):
        qty = int(_get_quantity_for_rate(rate_cfg, vision_surface))
        base_total = qty * float(rate_cfg["rate_eur"])
        line_items.append(
            {
                "surface_type": surface_type,
                "quantity": qty,
                "unit": "item",
                "unit_price_eur": float(rate_cfg["rate_eur"]),
                "base_total_eur": round(base_total, 2),
            }
        )

    elif unit == "fixed":
        base_total = float(rate_cfg["base_eur"])
        line_items.append(
            {
                "surface_type": surface_type,
                "unit": "fixed",
                "base_total_eur": round(base_total, 2),
            }
        )
    else:
        return {
            "status": "pricing_blocked",
            "reason": "UNKNOWN_UNIT",
            "surface_type": surface_type,
            "unit": rate_cfg.get("unit"),
        }

    # -------------------------
    # Multipliers
    # -------------------------
    multipliers_cfg = rules.get("multipliers", {})

    prep_multipliers = multipliers_cfg.get("prep_level", {})
    prep_level = vision_surface.get("prep_level")
    prep_multiplier = float(prep_multipliers.get(prep_level, 1.0))

    access_multipliers = multipliers_cfg.get("access_risk", {})
    access_risk = vision_surface.get("access_risk")
    access_multiplier = float(access_multipliers.get(access_risk, 1.0))

    complexity_cfg = multipliers_cfg.get("complexity", {})
    raw_complexity = float(vision_surface.get("estimated_complexity", 1.0) or 1.0)
    complexity_level = complexity_bucket(raw_complexity)
    complexity_multiplier = float(complexity_cfg.get(complexity_level, 1.0))

    labor_multiplier = prep_multiplier * access_multiplier * complexity_multiplier
    labor_cost = base_total * labor_multiplier

    # -------------------------
    # Cost split
    # -------------------------
    split_cfg = rules.get("cost_split", {})
    labor_ratio = float(split_cfg.get("labor_ratio", 1.0))
    materials_ratio = float(split_cfg.get("materials_ratio", 0.0))

    labor_eur = labor_cost * labor_ratio
    materials_eur = base_total * materials_ratio
    cost_eur = labor_eur + materials_eur

    # -------------------------
    # Margin
    # -------------------------
    margin_cfg = rules.get("margin", {})
    target_margin = float(margin_cfg.get("target", 0.0))
    min_margin = float(margin_cfg.get("minimum", 0.0))
    margin_rate = max(target_margin, min_margin)

    margin_eur = cost_eur * margin_rate
    total_eur = cost_eur + margin_eur

    item = line_items[-1]
    item.update(
        {
            "prep_level": prep_level,
            "prep_multiplier": prep_multiplier,
            "access_risk": access_risk,
            "access_multiplier": access_multiplier,
            "estimated_complexity": raw_complexity,
            "complexity_level": complexity_level,
            "complexity_multiplier": complexity_multiplier,
            "labor_eur": round(labor_eur, 2),
            "materials_eur": round(materials_eur, 2),
            "cost_eur": round(cost_eur, 2),
            "margin_rate": margin_rate,
            "margin_eur": round(margin_eur, 2),
            "total_eur": round(total_eur, 2),
        }
    )

    return {
        "status": "priced_with_margin",
        "currency": rules.get("currency", "EUR"),
        "base_total_eur": round(base_total, 2),
        "labor_eur": round(labor_eur, 2),
        "materials_eur": round(materials_eur, 2),
        "cost_eur": round(cost_eur, 2),
        "margin_rate": margin_rate,
        "margin_eur": round(margin_eur, 2),
        "total_eur": round(total_eur, 2),
        "ratios": {"labor": labor_ratio, "materials": materials_ratio},
        "line_items": line_items,
    }


# -------------------------
# Pipeline compatibility wrapper
# -------------------------
def run_pricing_engine(
    lead: Any,
    vision: Union[Dict[str, Any], list],
    rules: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Entry point used by engine step.
    - Prefer injecting rules from pipeline (tenant/market aware).
    - If not injected, we try to pick based on lead, else default.
    """
    if rules is None:
        rules = _pick_rules_from_lead(lead) or load_rules_default()

    if isinstance(vision, list):
        vision_surface = vision[0] if vision else {}
        return price_from_vision(vision_surface, rules=rules)

    return price_from_vision(vision if isinstance(vision, dict) else {}, rules=rules)


__all__ = [
    "run_pricing_engine",
    "price_from_vision",
    "load_rules_default",
    "load_rules_eu",
    "load_rules_us",
]
