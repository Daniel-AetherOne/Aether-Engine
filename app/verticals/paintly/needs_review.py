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
    area = (
        _get(estimate, "inputs.area_sqft", None)
        or _get(estimate, "square_feet", None)
        or _get(estimate, "meta.square_feet", None)
    )
    if area is not None:
        try:
            area_val = float(area)
            if area_val <= 0:
                soft.append("area_non_positive")
            if area_val > 20000:
                soft.append("area_too_large")
        except Exception:
            soft.append("area_not_numeric")

    # Escalate only if multiple soft signals
    if len(soft) >= 2:
        return soft

    return []
