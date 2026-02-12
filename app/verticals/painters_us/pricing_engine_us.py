from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, Union


# -------------------------
# Helpers
# -------------------------
def complexity_bucket(value: float) -> str:
    if value >= 1.3:
        return "high"
    if value >= 1.1:
        return "medium"
    return "low"


def load_us_rules() -> Dict[str, Any]:
    """
    Fallback loader (used if engine does not inject rules).
    """
    rules_path = Path(__file__).parent / "rules" / "pricing_rules_us.json"
    if not rules_path.exists():
        raise FileNotFoundError(f"Pricing rules not found: {rules_path}")
    return json.loads(rules_path.read_text(encoding="utf-8"))


# -------------------------
# Main pricing logic
# -------------------------
def price_from_vision(
    vision_surface: Dict[str, Any],
    rules: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    rules = rules or load_us_rules()

    # -------------------------
    # Gates (pricing_ready)
    # -------------------------
    gates = rules.get("gates", {})
    pricing_ready = bool(vision_surface.get("pricing_ready", False))

    if gates.get("require_pricing_ready", True) and not pricing_ready:
        rng_cfg = rules.get("estimate_range", {})
        low_factor = float(rng_cfg.get("low_factor", 0.85))
        high_factor = float(rng_cfg.get("high_factor", 1.15))

        base_rates = rules.get("base_rates", {})
        surface_type = vision_surface.get("surface_type")

        base_estimate = 0.0
        if surface_type in base_rates:
            rate_cfg = base_rates[surface_type]

            if rate_cfg.get("unit") == "sqft":
                sqft = float(vision_surface.get("sqft", 0) or 0)
                base_estimate = sqft * float(rate_cfg.get("rate_usd", 0.0))

            elif rate_cfg.get("unit") == "per_item":
                qty = int(vision_surface.get("count", 1))
                base_estimate = qty * float(rate_cfg.get("rate_usd", 0.0))

            elif rate_cfg.get("unit") == "fixed":
                base_estimate = float(rate_cfg.get("base_usd", 0.0))

        low = round(base_estimate * low_factor, 2)
        high = round(base_estimate * high_factor, 2)

        return {
            "status": "needs_review",
            "reason": "pricing_not_ready",
            "currency": rules.get("currency", "USD"),
            "needs_review": True,
            "total_usd": None,
            "estimate_range": {
                "low_usd": low,
                "high_usd": high,
                "basis": "base_rates_only",
                "factors": {"low": low_factor, "high": high_factor},
            },
            "surface_type": surface_type,
            "confidence": float(vision_surface.get("confidence", 0.0) or 0.0),
        }

    min_conf = float(gates.get("min_confidence", 0.0))
    conf = float(vision_surface.get("confidence", 0.0) or 0.0)
    if conf < min_conf:
        return {
            "status": "pricing_blocked",
            "reason": "low_confidence",
            "confidence": conf,
        }

    # -------------------------
    # Base rates
    # -------------------------
    base_rates = rules.get("base_rates", {})
    if not base_rates:
        return {
            "status": "no_pricing_defined",
            "total_usd": 0.0,
            "line_items": [],
        }

    surface_type = vision_surface.get("surface_type")
    if surface_type not in base_rates:
        return {
            "status": "pricing_blocked",
            "reason": "unsupported_surface_type",
            "surface_type": surface_type,
        }

    rate_cfg = base_rates[surface_type]
    line_items = []
    base_total = 0.0

    if rate_cfg["unit"] == "sqft":
        sqft = float(vision_surface.get("sqft", 0) or 0)
        base_total = sqft * float(rate_cfg["rate_usd"])
        line_items.append(
            {
                "surface_type": surface_type,
                "quantity": sqft,
                "unit": "sqft",
                "unit_price_usd": rate_cfg["rate_usd"],
                "base_total_usd": round(base_total, 2),
            }
        )

    elif rate_cfg["unit"] == "per_item":
        qty = int(vision_surface.get("count", 1))
        base_total = qty * float(rate_cfg["rate_usd"])
        line_items.append(
            {
                "surface_type": surface_type,
                "quantity": qty,
                "unit": "item",
                "unit_price_usd": rate_cfg["rate_usd"],
                "base_total_usd": round(base_total, 2),
            }
        )

    elif rate_cfg["unit"] == "fixed":
        base_total = float(rate_cfg["base_usd"])
        line_items.append(
            {
                "surface_type": surface_type,
                "unit": "fixed",
                "base_total_usd": round(base_total, 2),
            }
        )

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

    labor_usd = labor_cost * labor_ratio
    materials_usd = base_total * materials_ratio
    cost_usd = labor_usd + materials_usd

    # -------------------------
    # Margin
    # -------------------------
    margin_cfg = rules.get("margin", {})
    target_margin = float(margin_cfg.get("target", 0.0))
    min_margin = float(margin_cfg.get("minimum", 0.0))
    margin_rate = max(target_margin, min_margin)

    margin_usd = cost_usd * margin_rate
    total_usd = cost_usd + margin_usd

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
            "labor_usd": round(labor_usd, 2),
            "materials_usd": round(materials_usd, 2),
            "cost_usd": round(cost_usd, 2),
            "margin_rate": margin_rate,
            "margin_usd": round(margin_usd, 2),
            "total_usd": round(total_usd, 2),
        }
    )

    return {
        "status": "priced_with_margin",
        "currency": rules.get("currency", "USD"),
        "base_total_usd": round(base_total, 2),
        "labor_usd": round(labor_usd, 2),
        "materials_usd": round(materials_usd, 2),
        "cost_usd": round(cost_usd, 2),
        "margin_rate": margin_rate,
        "margin_usd": round(margin_usd, 2),
        "total_usd": round(total_usd, 2),
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
    """
    if isinstance(vision, list):
        vision_surface = vision[0] if vision else {}
        return price_from_vision(vision_surface, rules=rules)

    return price_from_vision(vision if isinstance(vision, dict) else {}, rules=rules)


__all__ = ["run_pricing_engine", "price_from_vision", "load_us_rules"]
