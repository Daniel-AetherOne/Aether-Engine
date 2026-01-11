from __future__ import annotations

from .base import D, BlockQuote, Rule, RuleResult, register
from ..calculators.net_cost import calc_net_cost


@register
class MinMarginRule(Rule):
    """
    MVP decision: minimum margin => BLOCK.
    params:
      min_margin_pct: 20  (meaning 20%)
    """
    type_name = "min_margin"

    def apply(self, ctx, line_state) -> RuleResult:
        qin = ctx.input
        data = ctx.data
        state = ctx.state

        min_pct = D(str(self.params.get("min_margin_pct", "0")))
        if min_pct <= 0:
            return RuleResult.skipped({"reason": "min_pct<=0"})

        net_cost = calc_net_cost(qin, data)

        if state.subtotal <= 0:
            raise BlockQuote(
                code="MARGIN_BLOCK",
                message="Subtotal must be > 0 to evaluate margin.",
                meta={"subtotal": str(state.subtotal), "net_cost": str(net_cost)},
            )

        margin_pct = (state.subtotal - net_cost) / state.subtotal * D("100")
        margin_pct_q = margin_pct.quantize(D("0.01"))

        if margin_pct < min_pct:
            raise BlockQuote(
                code="MARGIN_BLOCK",
                message="Minimum margin not met.",
                meta={
                    "min_margin_pct": str(min_pct),
                    "margin_pct": str(margin_pct_q),
                    "subtotal": str(state.subtotal),
                    "net_cost": str(net_cost),
                },
            )

        return RuleResult.applied(
            delta=D("0.00"),
            meta={"margin_pct": str(margin_pct_q), "min_margin_pct": str(min_pct)},
        )
