from __future__ import annotations

from typing import Any, Dict, List, Tuple


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

    This function should be conservative, but NOT block everything.
    Only flag NEEDS_REVIEW on real uncertainty / missing essentials.
    """
    reasons: List[str] = []

    if not isinstance(estimate, dict):
        return ["estimate_not_dict"]

    # --- Hard requirements (blockers) ---
    total = _get(estimate, "totals.total", None) or _get(estimate, "total", None)
    if total is None:
        reasons.append("missing_total")
    else:
        try:
            total_val = float(total)
            if total_val <= 0:
                reasons.append("non_positive_total")
        except Exception:
            reasons.append("total_not_numeric")

    # Area: allow missing, but if present and weird => review
    area = _get(estimate, "inputs.area_sqft", None) or _get(
        estimate, "square_feet", None
    )
    if area is not None:
        try:
            area_val = float(area)
            if area_val <= 0:
                reasons.append("area_non_positive")
            if area_val > 20000:  # sanity guard
                reasons.append("area_too_large")
        except Exception:
            reasons.append("area_not_numeric")

    # --- Soft signals (only review if multiple) ---
    soft: List[str] = []

    # If you have line items, good. If not, soft warning.
    items = _get(estimate, "items", None) or _get(estimate, "line_items", None)
    if not items or (isinstance(items, list) and len(items) == 0):
        soft.append("no_line_items")

    # Vision confidence if present
    conf = _get(estimate, "meta.confidence", None) or _get(estimate, "confidence", None)
    if conf is not None:
        try:
            c = float(conf)
            if c < 0.45:
                reasons.append("confidence_low")  # treat very low as blocker
            elif c < 0.65:
                soft.append("confidence_medium")
        except Exception:
            soft.append("confidence_not_numeric")

    # If total is suspiciously low/high -> soft warning
    if total is not None:
        try:
            tv = float(total)
            if tv < 200:
                soft.append("total_very_low")
            if tv > 25000:
                soft.append("total_very_high")
        except Exception:
            pass

    # If we already have blockers, return now
    if reasons:
        return reasons

    # Escalate only if multiple soft signals
    if len(soft) >= 2:
        return soft

    return []
