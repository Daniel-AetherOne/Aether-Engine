# app/verticals/painters_us/vision_aggregate_us.py
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple


def _ensure_obj(x: Any) -> Any:
    if isinstance(x, str):
        try:
            return json.loads(x)
        except Exception:
            return x
    return x


def _ensure_list_of_dicts(x: Any) -> List[Dict[str, Any]]:
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


def _avg(nums: List[float]) -> float:
    return sum(nums) / max(len(nums), 1)


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _bool_any(preds: List[Dict[str, Any]], issue: str) -> bool:
    # predictor returns issues like ["scheuren", "vocht"] or ["geen"]
    for p in preds:
        issues = p.get("issues") or []
        if isinstance(issues, str):
            issues = [issues]
        if issue in issues:
            return True
    return False


def _wall_repair_or_wallpaper_likely(preds: List[Dict[str, Any]]) -> bool:
    """
    MVP heuristic:
    detect obvious heavy prep / wallpaper removal / damaged substrate situations
    from loosely structured issue labels coming from vision.
    """
    repair_keywords = {
        "scheuren",
        "vocht",
        "behang",
        "behang_verwijderen",
        "wallpaper",
        "wallpaper_removal",
        "loslatend",
        "afbladderen",
        "peeling",
        "schade",
        "damage",
        "repair",
        "plamuur",
        "filler",
        "rough_wall",
        "ruwe_muur",
        "exposed_plaster",
        "stuc_zichtbaar",
    }

    for p in preds:
        issues = p.get("issues") or []
        if isinstance(issues, str):
            issues = [issues]

        # direct issue match
        for issue in issues:
            try:
                s = str(issue).strip().lower()
            except Exception:
                continue
            if s in repair_keywords:
                return True

        # optional free-text fields if your predictor emits them
        for key in ("label", "description", "notes", "summary"):
            val = p.get(key)
            if not val:
                continue
            try:
                s = str(val).strip().lower()
            except Exception:
                continue
            for kw in repair_keywords:
                if kw in s:
                    return True

    return False


def _collect_issue_evidence(
    preds: List[Dict[str, Any]],
) -> Tuple[Dict[str, bool], List[Dict[str, Any]]]:
    """
    Build a simple evidence list from predictor issues + substrate_confidence.
    Evidence is intentionally lightweight & backwards-compatible (plain dicts).
    """
    evidences: List[Dict[str, Any]] = []

    def add_evidence(key: str, present: bool, conf: float, value: Any = None) -> None:
        if not present:
            return
        evidences.append(
            {
                "key": key,
                "value": value if value is not None else True,
                "confidence": round(_clamp01(conf), 3),
                "source": "vision",
            }
        )

    # Avg substrate confidence (single scalar we can reuse)
    confs: List[float] = []
    for p in preds:
        try:
            confs.append(float(p.get("substrate_confidence", 0.0) or 0.0))
        except Exception:
            confs.append(0.0)
    vision_conf = _clamp01(_avg(confs)) if preds else 0.0

    # Known issues (current model)
    has_cracks = _bool_any(preds, "scheuren")
    has_moisture = _bool_any(preds, "vocht")

    add_evidence("issue_cracks", has_cracks, vision_conf, value="scheuren")
    add_evidence("issue_moisture", has_moisture, vision_conf, value="vocht")

    # Optional future issues (safe: won't trigger if not present)
    has_height = (
        _bool_any(preds, "hoogte")
        or _bool_any(preds, "trap")
        or _bool_any(preds, "moeilijk_bereikbaar")
    )
    add_evidence("issue_access", has_height, vision_conf, value="access")

    flags = {
        "cracks": bool(has_cracks),
        "moisture": bool(has_moisture),
        "access": bool(has_height),
    }

    return flags, evidences


def _derive_decision_vars(
    flags: Dict[str, bool], scope: Dict[str, Any]
) -> Dict[str, str]:
    """
    Decision vars are the stable contract between vision aggregation and pricing.
    Levels: low/medium/high (internally).
    We keep legacy prep_level light/medium/heavy in modifiers for backwards compat.
    """
    # Prep level (low/medium/high)
    prep = "medium"
    if flags.get("cracks"):
        prep = "medium"
    if flags.get("moisture"):
        prep = "high"
    if not flags.get("cracks") and not flags.get("moisture"):
        prep = "low"

    # Complexity level (low/medium/high)
    complexity_level = "medium"
    # scope can increase complexity even without vision hits
    paint_ceiling = bool(scope.get("paint_ceiling", False))
    paint_trim = bool(scope.get("paint_trim", False))
    if paint_ceiling or paint_trim:
        complexity_level = "high"
    if flags.get("cracks") or flags.get("moisture"):
        complexity_level = "high"

    # Access risk (low/medium/high)
    access = "low"
    if flags.get("access") or paint_ceiling:
        access = "medium"
    # moisture often correlates with awkward corners/ceilings; keep it conservative
    if flags.get("access") and paint_ceiling:
        access = "high"

    return {
        "prep_level": prep,
        "complexity_level": complexity_level,
        "access_risk": access,
    }


def _confidence_from_evidence(
    evidences: List[Dict[str, Any]], keys: List[str], default: float = 0.35
) -> float:
    vals: List[float] = []
    for e in evidences:
        if e.get("key") in keys:
            try:
                vals.append(float(e.get("confidence", 0.0) or 0.0))
            except Exception:
                vals.append(0.0)
    if not vals:
        return _clamp01(default)
    return _clamp01(sum(vals) / len(vals))


def _overall_conf(prep: float, comp: float, access: float) -> float:
    # conservative overall confidence
    return _clamp01(min(prep, comp, access))


def _legacy_modifiers_from_levels(
    decision_vars: Dict[str, str], flags: Dict[str, bool]
) -> Dict[str, Any]:
    """
    Backwards-compatible modifiers:
    - prep_level must match existing: light/medium/heavy
    - complexity is a numeric multiplier (float)
    """
    # Map low/medium/high -> light/medium/heavy
    prep_map = {"low": "light", "medium": "medium", "high": "heavy"}
    legacy_prep = prep_map.get(decision_vars["prep_level"], "medium")

    # Complexity multiplier from complexity_level
    comp_level = decision_vars["complexity_level"]
    comp_mult_map = {"low": 0.95, "medium": 1.00, "high": 1.15}
    complexity = float(comp_mult_map.get(comp_level, 1.00))

    # Keep your old additional bumps based on flags (conservative)
    if flags.get("cracks"):
        complexity += 0.10
    if flags.get("moisture"):
        complexity += 0.15

    complexity = max(0.9, min(complexity, 1.35))

    return {
        "prep_level": legacy_prep,
        "complexity": round(complexity, 2),
        "risk": {
            "cracks": bool(flags.get("cracks")),
            "moisture": bool(flags.get("moisture")),
            "access": bool(flags.get("access")),
        },
    }


def _sanity_check_area(area_m2: Optional[float]) -> Dict[str, Any]:
    # MVP guardrails. Later refine with scope/roomcount.
    if area_m2 is None:
        return {"status": "UNKNOWN", "reason": "no_area"}

    if area_m2 < 8:
        return {"status": "REVIEW", "reason": "area_too_small"}
    if area_m2 > 250:
        return {"status": "REVIEW", "reason": "area_too_large"}

    return {"status": "OK", "reason": None}


def _area_range(area_m2: Optional[float]) -> Optional[Dict[str, float]]:
    """
    MVP: give pricing a safe +/- band to use later if you want.
    Not used by pricing_engine yet, but useful for future confidence/range quotes.
    """
    if area_m2 is None:
        return None
    try:
        a = float(area_m2)
    except Exception:
        return None

    low = max(0.0, round(a * 0.85, 2))
    high = round(a * 1.15, 2)
    return {"low_m2": low, "mid_m2": round(a, 2), "high_m2": high}


def aggregate_images_to_quote_inputs(
    image_predictions: Any,
    estimated_area_m2: Optional[float] = None,
    scope: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    MVP:
    - area comes from customer estimate (estimated_area_m2)
    - vision provides decision vars (prep/complexity/access) + confidence bundle + evidences
    - pricing_ready == True if area is present and sane enough to compute a price
    - needs_review flags risky situations (area too small/large, too few images, low confidence, etc.)
    """

    # Backwards compat: some pipelines call this without estimated_area_m2
    if estimated_area_m2 is None and isinstance(scope, dict):
        for k in ("estimated_area_m2", "area_m2", "square_meters", "sqm"):
            v = scope.get(k)
            try:
                if v is not None:
                    estimated_area_m2 = float(v)
                    break
            except Exception:
                pass

    preds = _ensure_list_of_dicts(image_predictions)

    # default scope
    scope = scope or {
        "interior": True,
        "paint_walls": True,
        "paint_ceiling": False,
        "paint_trim": False,
    }

    # Base vision signal confidence = avg substrate_confidence (NOT area confidence)
    confs: List[float] = []
    for p in preds:
        try:
            confs.append(float(p.get("substrate_confidence", 0.0) or 0.0))
        except Exception:
            confs.append(0.0)
    vision_conf = round(_avg(confs), 3) if preds else 0.0

    flags, evidences = _collect_issue_evidence(preds)
    decision_vars = _derive_decision_vars(flags, scope)
    heavy_prep_likely = _wall_repair_or_wallpaper_likely(preds)

    # Per-variable confidence (MVP): evidence-based; defaults conservative
    prep_conf = _confidence_from_evidence(
        evidences, keys=["issue_cracks", "issue_moisture"], default=0.45
    )
    complexity_conf = _confidence_from_evidence(
        evidences, keys=["issue_cracks", "issue_moisture"], default=0.45
    )
    access_conf = _confidence_from_evidence(
        evidences, keys=["issue_access"], default=0.40
    )

    overall = round(_overall_conf(prep_conf, complexity_conf, access_conf), 3)

    sanity = _sanity_check_area(estimated_area_m2)

    review_reasons: List[str] = []
    needs_review = False

    # Area sanity
    if sanity["status"] == "REVIEW":
        needs_review = True
        review_reasons.append(sanity["reason"])

    # Image count sanity
    if len(preds) == 0:
        needs_review = True
        review_reasons.append("no_images")

    elif len(preds) == 1 and overall < 0.55:
        needs_review = True
        review_reasons.append("few_images_low_confidence")

    # MVP guardrail: obvious heavy prep / wallpaper removal / damaged wall
    if heavy_prep_likely:
        needs_review = True
        review_reasons.append("wall_repair_or_wallpaper_likely")

    # Confidence-based review (new, explicit)
    if overall < 0.55:
        needs_review = True
        review_reasons.append("low_overall_confidence")

    if heavy_prep_likely:
        decision_vars["prep_level"] = "high"
        decision_vars["complexity_level"] = "high"

    # Keep old guardrail behavior: if vision signal is weak, bias complexity upward (prevents underquotes)
    legacy_mods = _legacy_modifiers_from_levels(decision_vars, flags)
    if vision_conf < 0.6:
        needs_review = True
        review_reasons.append("low_vision_signal_confidence")
        legacy_mods["complexity"] = max(float(legacy_mods.get("complexity", 1.0)), 1.1)

    # pricing_ready: area must exist & not obviously nonsense
    pricing_ready = (estimated_area_m2 is not None) and (estimated_area_m2 >= 8)

    # dedupe reasons
    review_reasons = list(dict.fromkeys(review_reasons))

    return {
        "area": {
            "value_m2": estimated_area_m2,
            "range": _area_range(estimated_area_m2),
            "source": "customer_estimate",
            "confidence": (
                0.75 if estimated_area_m2 else 0.0
            ),  # placeholder (intake confidence)
            "sanity": sanity,
        },
        "scope": scope,
        # Backwards-compatible pricing knobs (existing pricing_engine can keep working)
        "modifiers": legacy_mods,
        # New stable contract for Step B -> pricing multipliers + explainability
        "decision_vars": decision_vars,  # prep_level/complexity_level/access_risk (low/medium/high)
        "confidence": {
            "prep_conf": round(_clamp01(prep_conf), 3),
            "complexity_conf": round(_clamp01(complexity_conf), 3),
            "access_conf": round(_clamp01(access_conf), 3),
            "overall": overall,
        },
        "evidences": evidences,
        "vision_signal_confidence": vision_conf,
        # IMPORTANT: pricing_ready should NOT be disabled by needs_review
        "pricing_ready": bool(pricing_ready),
        "needs_review": bool(needs_review),
        "review_reasons": review_reasons,
    }


# Backwards-compat alias (older code expects this name)
aggregate_images_to_surfaces = aggregate_images_to_quote_inputs
