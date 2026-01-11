from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Tuple

from ..engine.context import ActiveData

D = Decimal


def calc_tier_discount_delta(subtotal: D, data: ActiveData, params: Dict[str, Any]) -> Tuple[D, Dict[str, Any]]:
    """
    params:
      tiers:
        - min: 0
          percent: 0
        - min: 1000
          percent: 3
        - min: 2500
          percent: 5
    """
    tiers: List[Dict[str, Any]] = list(params.get("tiers") or [])
    if not tiers:
        return D("0.00"), {"reason": "no_tiers"}

    # kies hoogste tier waarvoor subtotal >= min
    chosen = None
    for t in tiers:
        tmin = D(str(t.get("min", "0")))
        if subtotal >= tmin:
            if chosen is None or tmin >= D(str(chosen.get("min", "0"))):
                chosen = t

    if not chosen:
        return D("0.00"), {"reason": "no_match"}

    pct = D(str(chosen.get("percent", "0")))
    if pct <= 0:
        return D("0.00"), {"pct": str(pct), "tier": chosen}

    delta = (subtotal * pct / D("100")) * D("-1")
    return delta.quantize(D("0.01")), {"pct": str(pct), "tier_min": str(chosen.get("min"))}
