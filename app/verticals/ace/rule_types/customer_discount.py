from __future__ import annotations

from .base import D, Rule, RuleResult, register
from ..calculators.customer_discount import calc_customer_discount_delta


@register
class CustomerDiscountRule(Rule):
    type_name = "customer_discount"

    def apply(self, ctx, line_state) -> RuleResult:
        qin = ctx.input
        subtotal = ctx.state.subtotal

        delta, meta = calc_customer_discount_delta(qin=qin, subtotal=subtotal, params=self.params)
        if delta == D("0.00"):
            return RuleResult.skipped(meta | {"reason": "delta=0"})
        return RuleResult.applied(delta=delta, meta=meta)
