from __future__ import annotations

from .base import D, Rule, RuleResult, register


@register
class CustomerDiscountRule(Rule):
    """
    3.5.4 — Klantkorting + plafond (per line)

    Explain (FASE 4.3):
      - 1 entry alleen als pct > 0: CUSTOMER_DISCOUNT
      - geen "−0%" entries (Policy A)
      - warning bij cap blijft via ctx.warn
    """

    type_name = "customer_discount"

    def apply(self, ctx, line_state) -> RuleResult:
        segment = (ctx.input.customer_segment or "A").strip().upper()

        profile_map = (ctx.data.tables or {}).get("customer_profile_discount_pct") or {"A": "0", "B": "2", "C": "4"}
        max_extra_map = (ctx.data.tables or {}).get("customer_max_extra_discount_pct") or {"A": "0", "B": "2", "C": "4"}

        pct = D(str(profile_map.get(segment, "0")))
        max_pct = D(str(max_extra_map.get(segment, "0")))

        # MVP: requested extra discount comes from ctx.input.discount_percent (optional)
        requested = ctx.input.discount_percent
        extra = D(str(requested)) if requested is not None else D("0")

        # Enforce ceiling
        if extra > max_pct:
            extra = max_pct
            ctx.warn(
                "DISCOUNT_CAPPED",
                "Requested discount capped by profile max.",
                segment=segment,
                cappedTo=str(max_pct),
            )

        total_pct = (pct + extra).quantize(D("0.01"))
        line_state.customer_discount_pct = total_pct

        if total_pct <= D("0.00"):
            # Policy A: niet tonen
            return RuleResult.skipped({"segment": segment, "pct": "0"})

        # Apply discount on current net_sell
        before = line_state.net_sell
        factor = (D("1.0") - (total_pct / D("100")))
        after = (before * factor).quantize(D("0.01"))
        line_state.net_sell = after

        # Policy A: 1 entry (alleen bij pct>0)
        line_state.breakdown.add_step(
            "CUSTOMER_DISCOUNT",
            f"Klantkorting ({segment}): -{total_pct}% (van {before} naar {after})",
        )

        return RuleResult.applied(
            D("0.00"),
            {"segment": segment, "pct": str(total_pct), "before": str(before), "after": str(after)},
        )
