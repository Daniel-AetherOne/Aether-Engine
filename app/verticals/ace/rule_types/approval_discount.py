from __future__ import annotations

from decimal import Decimal
from .base import D, Rule, RuleResult, register


@register
class ApprovalDiscountRule(Rule):
    type_name = "approval_discount"

    def apply(self, ctx, line_state) -> RuleResult:
        requested = ctx.input.discount_percent
        if requested is None:
            return RuleResult.skipped({"reason": "no_requested_discount"})

        segment = (ctx.input.customer_segment or "A").strip().upper()
        max_extra_map = (ctx.data.tables or {}).get(
            "customer_max_extra_discount_pct"
        ) or {"A": "0", "B": "2", "C": "4"}
        max_pct = D(str(max_extra_map.get(segment, "0")))

        req = D(str(requested))
        if req > max_pct:
            ctx.warn(
                "APPROVAL_REQUIRED",
                "Requested discount exceeds profile allowance; approval required.",
                segment=segment,
                requested=str(req),
                allowed=str(max_pct),
                lineId=line_state.line_id,
                sku=line_state.sku,
            )
            line_state.add_breakdown(
                f"Approval: extra korting {req}% > profiel {max_pct}% (approval vereist)"
            )
            return RuleResult.applied(D("0.00"), {"approval_required": True})

        return RuleResult.skipped({"approval_required": False})
