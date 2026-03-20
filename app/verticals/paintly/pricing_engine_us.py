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
    return _load_rules_file("paintly_price_rules_eu.json")


def load_rules_us() -> Dict[str, Any]:
    return _load_rules_file("pricing_rules_us.json")


def load_rules_eu() -> Dict[str, Any]:
    return _load_rules_file("paintly_price_rules_eu.json")


def _pick_rules_from_lead(lead: Any) -> Optional[Dict[str, Any]]:
    """
    Optional: auto-select rules based on lead / tenant metadata.
    If you already inject `rules` from the pipeline, you can ignore this.
    """
    market = None
    locale = None

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

    if "us" in key or "en-us" in key or "usa" in key:
        return load_rules_us()
    if "nl" in key or "eu" in key or "europe" in key or "en-nl" in key:
        return load_rules_eu()

    return None


def _safe_float(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        f = float(v)
        return f
    except (TypeError, ValueError):
        return None


def _tenant_money(pricing: Dict[str, Any], *keys: str) -> Optional[float]:
    for key in keys:
        if key in pricing:
            value = _safe_float(pricing.get(key))
            if value is not None:
                return value
    return None


def _extract_intake_payload(lead: Any) -> Dict[str, Any]:
    raw = getattr(lead, "intake_payload", None)
    if not raw:
        return {}
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _inject_overrides_from_lead(
    lead: Any, vision_surface: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Make pricing robust during EU migration:
    - If vision didn't provide area, pull from lead.square_meters or intake_payload overrides.
    - If vision didn't provide surface_type, default to 'walls' (interior paint baseline).
    """
    vs: Dict[str, Any] = dict(vision_surface or {})

    # 1) Area from lead column
    sqm = _safe_float(getattr(lead, "square_meters", None))
    if sqm and sqm > 0:
        vs.setdefault("area_sqm", sqm)
        vs.setdefault("sqm", sqm)

    # 2) Area + job_type from intake_payload
    payload = _extract_intake_payload(lead)

    sqm2 = _safe_float(payload.get("square_meters")) or _safe_float(
        payload.get("area_sqm")
    )
    if sqm2 and sqm2 > 0:
        vs.setdefault("area_sqm", sqm2)
        vs.setdefault("sqm", sqm2)

    # NEW: job_type from intake
    job_type = payload.get("job_type")
    if job_type:
        vs.setdefault("job_type", job_type)

    # 3) Surface type fallback (critical: base_rates lookup)
    if not vs.get("surface_type"):
        vs["surface_type"] = "walls"

    return vs


def _get_area_sqm(vision_surface: Dict[str, Any]) -> float:
    """
    Canonical area for EU: sqm.
    Supports multiple possible keys from your vision/metrics pipeline.
    """
    for k in ("area_sqm", "total_area_sqm", "wall_area_sqm", "ceiling_area_sqm", "sqm"):
        v = vision_surface.get(k)
        if v is not None:
            try:
                return float(v or 0)
            except (TypeError, ValueError):
                pass

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
        return _get_area_sqm(vision_surface) * SQM_TO_SQFT

    if unit in ("per_item", "item", "items"):
        try:
            return float(int(vision_surface.get("count", 1)))
        except (TypeError, ValueError):
            return 1.0

    if unit == "fixed":
        return 1.0

    return 0.0


def _has_pricing_area(rate_cfg: Dict[str, Any], vision_surface: Dict[str, Any]) -> bool:
    unit = (rate_cfg.get("unit") or "").lower()
    if unit in ("sqm", "sqft"):
        return _get_quantity_for_rate(rate_cfg, vision_surface) > 0
    return True


# -------------------------
# Adapter for quote_inputs (photo-assisted MVP)
# -------------------------
def _map_level3_to_prep_legacy(level: str) -> str:
    # Legacy prep levels in your pipeline: light/medium/heavy
    m = {
        "low": "light",
        "medium": "medium",
        "high": "heavy",
    }
    return m.get((level or "").lower(), "medium")


def _map_level3_to_access_legacy(level: str) -> str:
    # Pricing rules expect access_risk buckets like low/medium/high
    m = {"low": "low", "medium": "medium", "high": "high"}
    return m.get((level or "").lower(), "low")


def _complexity_multiplier_from_level(level: str) -> float:
    """
    We store a numeric 'estimated_complexity' so the existing complexity_bucket() keeps working.
    Bucket thresholds:
      >= 1.3 -> high
      >= 1.1 -> medium
      else -> low
    """
    m = {
        "low": 1.0,  # -> low bucket
        "medium": 1.15,  # -> medium bucket
        "high": 1.3,  # -> high bucket
    }
    try:
        return float(m.get((level or "").lower(), 1.0))
    except Exception:
        return 1.0


def _quote_inputs_to_surface(q: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert quote_inputs from vision_aggregate_us.py into a pricing surface dict
    expected by price_from_vision().

    Supports BOTH:
    - legacy q["modifiers"] (prep_level light/medium/heavy + complexity float)
    - new q["decision_vars"] + q["confidence"] (+ evidences/review reasons)
    """
    area = q.get("area") if isinstance(q.get("area"), dict) else {}
    mods = q.get("modifiers") if isinstance(q.get("modifiers"), dict) else {}
    dv = q.get("decision_vars") if isinstance(q.get("decision_vars"), dict) else {}
    conf_bundle = q.get("confidence") if isinstance(q.get("confidence"), dict) else {}

    area_m2 = _safe_float(area.get("value_m2"))

    # --- Decide which source to use (new decision_vars wins) ---
    if dv:
        prep_level = _map_level3_to_prep_legacy(
            dv.get("prep_level") or dv.get("prep") or "medium"
        )
        access_risk = _map_level3_to_access_legacy(
            dv.get("access_risk") or dv.get("access") or "low"
        )

        # complexity_level -> numeric estimated_complexity so existing engine keeps working
        complexity_level = (
            dv.get("complexity_level") or dv.get("complexity") or "medium"
        )
        estimated_complexity = _complexity_multiplier_from_level(str(complexity_level))
    else:
        # legacy path
        prep_level = mods.get("prep_level") or "medium"
        access_risk = "low"
        estimated_complexity = _safe_float(mods.get("complexity")) or 1.0

    # --- Confidence gating signal ---
    sig = _safe_float(q.get("vision_signal_confidence")) or 0.0
    overall = _safe_float(conf_bundle.get("overall")) if conf_bundle else None
    base_conf = float(overall) if overall is not None else float(sig)

    # Confidence floor: if customer provided area, don't block pricing on vision confidence
    conf = max(base_conf, 0.7) if (area_m2 and area_m2 > 0) else base_conf

    return {
        "surface_type": "walls",
        "pricing_ready": bool(q.get("pricing_ready", False)),
        "area_sqm": area_m2,
        "prep_level": prep_level,
        "access_risk": access_risk,
        "estimated_complexity": float(estimated_complexity),
        "confidence": float(conf),
        # optional debug/meta for downstream output builder / HTML
        "meta": {
            "sig_conf": sig,
            "overall_conf": overall,
            "area_source": area.get("source"),
            "needs_review": bool(q.get("needs_review", False)),
            "review_reasons": q.get("review_reasons", []),
            "decision_vars": dv,
            "evidences": q.get("evidences", []),
        },
    }


# -------------------------
# Main pricing logic
# -------------------------
def price_from_vision(
    vision_surface: Dict[str, Any],
    rules: Optional[Dict[str, Any]] = None,
    tenant_pricing: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    rules = rules or load_rules_default()

    # -------------------------
    # Gates
    # -------------------------
    gates = rules.get("gates", {})

    pricing_ready = bool(vision_surface.get("pricing_ready", False))
    require_pricing_ready = bool(gates.get("require_pricing_ready", False))

    min_conf = float(gates.get("min_confidence", 0.0))
    conf = float(vision_surface.get("confidence", 0.0) or 0.0)
    area_ok = _get_area_sqm(vision_surface) > 0

    # Only block on confidence if we also lack area (otherwise we can still price & flag review)
    if (not area_ok) and conf < min_conf:
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

    rate_cfg = dict(base_rates[surface_type] or {})

    tenant_pricing = tenant_pricing if isinstance(tenant_pricing, dict) else {}
    tenant_price_per_m2 = _tenant_money(
        tenant_pricing,
        "price_per_m2",
        "walls_rate_eur_per_sqm",
    )
    tenant_minimum_price = _tenant_money(
        tenant_pricing,
        "minimum_price",
        "minimum_prijs",
        "minimum_price_eur",
    )
    tenant_travel_cost = _tenant_money(
        tenant_pricing,
        "callout_fee",
        "voorrijkosten",
        "travel_cost_eur",
    )

    if (
        surface_type == "walls"
        and (rate_cfg.get("unit") or "").lower() == "sqm"
        and tenant_price_per_m2 is not None
        and tenant_price_per_m2 > 0
    ):
        rate_cfg["rate_eur"] = float(tenant_price_per_m2)

    # If pricing_ready is required, allow a range estimate (instead of €0)
    if require_pricing_ready and not pricing_ready:
        rng_cfg = rules.get("estimate_range", {})
        low_factor = float(rng_cfg.get("low_factor", 0.85))
        high_factor = float(rng_cfg.get("high_factor", 1.15))

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

    # NEW: job type multiplier (Binnenwerk / Buitenwerk / Beide)
    job_type_cfg = multipliers_cfg.get("job_type", {})
    job_type = vision_surface.get("job_type", "Binnenwerk")
    job_type_multiplier = float(job_type_cfg.get(job_type, 1.0))

    labor_multiplier = (
        prep_multiplier
        * access_multiplier
        * complexity_multiplier
        * job_type_multiplier
    )

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

    if tenant_minimum_price is not None and tenant_minimum_price > 0:
        total_eur = max(total_eur, float(tenant_minimum_price))
    if tenant_travel_cost is not None and tenant_travel_cost > 0:
        total_eur += float(tenant_travel_cost)

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
            "job_type": job_type,
            "job_type_multiplier": job_type_multiplier,
            "labor_eur": round(labor_eur, 2),
            "materials_eur": round(materials_eur, 2),
            "cost_eur": round(cost_eur, 2),
            "margin_rate": margin_rate,
            "margin_eur": round(margin_eur, 2),
            "total_eur": round(total_eur, 2),
            "tenant_price_per_m2": tenant_price_per_m2,
            "tenant_minimum_prijs": tenant_minimum_price,
            "tenant_voorrijkosten": tenant_travel_cost,
        }
    )

    # ---- Propagate review flags from upstream (aggregator) ----
    meta = (
        vision_surface.get("meta")
        if isinstance(vision_surface.get("meta"), dict)
        else {}
    )

    upstream_needs_review = bool(meta.get("needs_review", False))
    upstream_reasons = meta.get("review_reasons", [])
    if not isinstance(upstream_reasons, list):
        upstream_reasons = []

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
        # NEW: review + explainability
        "needs_review": upstream_needs_review,
        "review_reasons": upstream_reasons,
        "confidence": conf,
        # useful for HTML / debugging
        "decision_vars": meta.get("decision_vars"),
        "evidences": meta.get("evidences", []),
    }


# -------------------------
# Pipeline compatibility wrapper
# -------------------------


def run_pricing_engine(
    lead: Any,
    vision: Union[Dict[str, Any], list],
    rules: Optional[Dict[str, Any]] = None,
    tenant_pricing: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Entry point used by engine step.
    - Prefer injecting rules from pipeline (tenant/market aware).
    - If not injected, we try to pick based on lead, else default.
    Supports:
      - legacy vision_surface dict
      - legacy list[vision_surface]
      - NEW: quote_inputs dict (area/modifiers/scope + optional decision_vars/confidence/evidences)
    """
    if rules is None:
        rules = _pick_rules_from_lead(lead) or load_rules_default()

    # Normalize `vision` input
    if isinstance(vision, dict) and ("area" in vision and "modifiers" in vision):
        # quote_inputs shape from aggregator
        vision_surface = _quote_inputs_to_surface(vision)
    elif isinstance(vision, list):
        vision_surface = vision[0] if vision else {}
    else:
        vision_surface = vision if isinstance(vision, dict) else {}

    # Inject area + surface_type from lead/intake overrides (EU migration safety net)
    vision_surface = _inject_overrides_from_lead(lead, vision_surface)

    return price_from_vision(
        vision_surface,
        rules=rules,
        tenant_pricing=tenant_pricing,
    )


__all__ = [
    "run_pricing_engine",
    "price_from_vision",
    "load_rules_default",
    "load_rules_eu",
    "load_rules_us",
]
