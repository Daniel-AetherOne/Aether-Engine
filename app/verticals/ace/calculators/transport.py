from __future__ import annotations

from decimal import Decimal
from typing import Dict, Any, Tuple

from ..engine.context import ActiveData, QuoteInput

D = Decimal


def calc_transport_delta(qin: QuoteInput, data: ActiveData, params: Dict[str, Any]) -> Tuple[D, Dict[str, Any]]:
    per_km = D(str(params.get("per_km", "0.00")))
    km = qin.transport_km
    delta = (per_km * km).quantize(D("0.01"))
    return delta, {"km": str(km), "per_km": str(per_km)}
