from __future__ import annotations

from decimal import Decimal
from typing import Dict, Any, Tuple, Optional

from ..engine.context import QuoteInput

D = Decimal


def calc_customer_discount_delta(qin: QuoteInput, subtotal: D, params: Dict[str, Any]) -> Tuple[D, Dict[str, Any]]:
    # percent kan uit input komen, of uit params default
    pct: Optional[D] = qin.discount_percent
    if pct is None:
        pct = D(str(params.get("default_percent", "0")))

    if pct <= 0:
        return D("0.00"), {"pct": str(pct), "reason": "pct<=0"}

    # Discount verlaagt de prijs: delta is negatief
    delta = (subtotal * pct / D("100")) * D("-1")
    return delta.quantize(D("0.01")), {"pct": str(pct)}
