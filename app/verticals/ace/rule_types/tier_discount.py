from __future__ import annotations

from .base import D, Rule, RuleResult, register
from ..calculators.tier_discount import calc_tier_discount_delta


@register
class TierDiscountRule(Rule):
    type_name = "tier_discount"

    def apply(self, ctx, line_state) -> RuleResult:
        data = ctx.data
        subtotal = ctx.state.subtotal

        delta, meta = calc_tier_discount_delta(subtotal=subtotal, data=data, params=self.params)
        if delta == D("0.00"):
            return RuleResult.skipped(meta | {"reason": "delta=0"})
        return RuleResult.applied(delta=delta, meta=meta)
