from __future__ import annotations

from copy import deepcopy
from typing import Any


def get_tenant_pricing(tenant: Any) -> dict:
    if tenant is None:
        return {}
    pricing = getattr(tenant, "pricing_json", None)
    return pricing if isinstance(pricing, dict) else {}


def get_tenant_walls_rate(tenant: Any) -> float | None:
    pricing = get_tenant_pricing(tenant)
    value = pricing.get("walls_rate_eur_per_sqm")

    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def apply_paintly_tenant_pricing_overrides(rules: dict, tenant: Any) -> dict:
    effective_rules = deepcopy(rules or {})

    walls_rate = get_tenant_walls_rate(tenant)
    if walls_rate is None:
        return effective_rules

    base_rates = effective_rules.setdefault("base_rates", {})

    existing_walls_cfg = base_rates.get("walls")
    if not isinstance(existing_walls_cfg, dict):
        existing_walls_cfg = {}

    walls_cfg = {
        "unit": existing_walls_cfg.get("unit") or "sqm",
        **existing_walls_cfg,
        "rate_eur": float(walls_rate),
    }

    base_rates["walls"] = walls_cfg
    return effective_rules
