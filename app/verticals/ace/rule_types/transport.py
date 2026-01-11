from __future__ import annotations

from .base import D, Rule, RuleResult, register
from ..calculators.transport import calc_transport_delta


@register
class TransportRule(Rule):
    type_name = "transport"

    def apply(self, ctx, line_state) -> RuleResult:
        qin = ctx.input
        data = ctx.data

        delta, meta = calc_transport_delta(qin=qin, data=data, params=self.params)
        if delta == D("0.00"):
            return RuleResult.skipped(meta | {"reason": "delta=0"})
        return RuleResult.applied(delta=delta, meta=meta)
