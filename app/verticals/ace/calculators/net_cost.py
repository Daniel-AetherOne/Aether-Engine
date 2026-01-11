from __future__ import annotations

from decimal import Decimal
from ..engine.context import ActiveData, QuoteInput

D = Decimal


def calc_net_cost(qin: QuoteInput, data: ActiveData) -> D:
    # MVP: input-driven cost. Later uit dataset/tables.
    return (qin.material_cost + qin.labor_cost).quantize(D("0.01"))
