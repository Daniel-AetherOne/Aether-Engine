# app/verticals/paintly/needs_review.py
from __future__ import annotations

from typing import Any, Dict, List


US_PAINTERS_NEEDS_REVIEW_COPY = {
    "headline": "Thanks — we’ll review this and get back to you shortly.",
    "body": (
        "Your project needs a quick manual check to make sure the estimate is accurate. "
        "You don’t need to do anything right now."
    ),
}

PAINTLY_NEEDS_REVIEW_COPY = {
    "intro": "We hebben nog een korte handmatige check nodig om de prijs 100% zeker te maken.",
    "range_explanation": "We bevestigen oppervlakken, voorbereiding en bereikbaarheid. Daarna ontvang je de definitieve prijs.",
}


def _get(d: Dict[str, Any], path: str, default=None):
    cur: Any = d
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def needs_review_from_output(estimate: Any) -> List[str]:
    """
    Returns a list of reasons. Empty list => OK to auto-deliver.

    "Preset B" (recommended):
    - Block only on truly broken output (missing/invalid total).
    - Otherwise: only flag NEEDS_REVIEW when 2+ soft signals stack up.
    """
    if not isinstance(estimate, dict):
        return ["estimate_not_dict"]

    reasons: List[str] = []
    soft: List[str] = []

    # ------------------------------------------------------------------
    # HARD requirement: we must have a non-zero total
    # NOTE: PricingOutput uses totals.grand_total (and totals.pre_tax).
    # ------------------------------------------------------------------
    total = (
        _get(estimate, "totals.grand_total", None)
        or _get(estimate, "totals.pre_tax", None)
        or _get(estimate, "total_eur", None)
        or _get(estimate, "total", None)
    )

    if total is None:
        reasons.append("missing_total")
    else:
        try:
            total_val = float(total)
            if total_val <= 0:
                reasons.append("non_positive_total")
        except Exception:
            reasons.append("total_not_numeric")

    # If we already have blockers, stop here
    if reasons:
        return reasons

    # ------------------------------------------------------------------
    # SOFT signals (only escalate if multiple)
    # ------------------------------------------------------------------

    # Vision wants manual review (MVP safety rail)
    vision_needs_review = _get(estimate, "meta.vision_needs_review", None)
    if vision_needs_review is True:
        # treat as a soft signal; it will trigger review if another soft signal is present
        soft.append("vision_needs_review")

        # add the specific reasons (also soft)
        vr = _get(estimate, "meta.vision_review_reasons", None)
        if isinstance(vr, list):
            for r in vr:
                if isinstance(r, str) and r:
                    soft.append(f"vision:{r}")

    # Line items presence
    items = _get(estimate, "line_items", None) or _get(estimate, "items", None)
    if not items or (isinstance(items, list) and len(items) == 0):
        soft.append("no_line_items")

    # Vision confidence if present (optional field)
    conf = _get(estimate, "meta.confidence", None) or _get(estimate, "confidence", None)
    if conf is not None:
        try:
            c = float(conf)
            if c < 0.45:
                # very low confidence -> treat as blocker-ish (but still "soft" bucket)
                # if you want this to be a hard blocker, move to `reasons.append(...)`
                soft.append("confidence_low")
            elif c < 0.65:
                soft.append("confidence_medium")
        except Exception:
            soft.append("confidence_not_numeric")

    # Suspiciously low/high totals (tune as you like)
    try:
        tv = float(total)
        if tv < 200:
            soft.append("total_very_low")
        if tv > 25000:
            soft.append("total_very_high")
    except Exception:
        pass

    # Area checks (optional; only if you actually store it in output)
    # Keep this non-blocking.
    area_m2 = _get(estimate, "meta.area_m2", None) or _get(
        estimate, "inputs.area_m2", None
    )
    if area_m2 is not None:
        try:
            a = float(area_m2)
            if a < 8:
                soft.append("area_m2_too_small")
            if a > 250:
                soft.append("area_m2_too_large")
        except Exception:
            soft.append("area_m2_not_numeric")

    # Escalate only if multiple soft signals
    if len(soft) >= 2:
        return soft

    return []
