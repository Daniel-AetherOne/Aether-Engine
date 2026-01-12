from __future__ import annotations

from .base import D, BlockQuote, Rule, RuleResult, register


@register
class MinMarginRule(Rule):
    """
    Minimummarge rule (policy A: BLOCK).
    Adds explain entry always (OK/BLOCK) via line_state.breakdown.
    """

    type_name = "min_margin"

    def apply(self, ctx, line_state) -> RuleResult:
        sell = line_state.net_sell

        # Always visible check (BLOCK)
        if sell <= 0:
            line_state.breakdown.add_check(
                "MIN_MARGIN_BLOCK",
                "Minimummarge: BLOCK (sell <= 0)",
                status="BLOCK",
            )
            # keep backwards compatible string too (some tests might search)
            line_state.add_breakdown("Minimummarge: BLOCK (sell <= 0)")

            raise BlockQuote(
                "MARGIN_BLOCK",
                "Sell price must be > 0 to evaluate margin.",
                {"sell": str(sell)},
            )

        cost = (line_state.net_cost + line_state.transport_cost).quantize(D("0.01"))
        margin_pct = ((sell - cost) / sell * D("100")).quantize(D("0.01"))
        line_state.margin_pct = margin_pct

        group = line_state.article.product_group if line_state.article else None
        m = (ctx.data.tables or {}).get("min_margin_pct_by_group") or {}
        min_pct = D(str(m.get(group, "20")))

        if margin_pct < min_pct:
            # Always visible check (BLOCK)
            line_state.breakdown.add_check(
                "MIN_MARGIN_BLOCK",
                f"Minimummarge: BLOCK ({margin_pct}% < {min_pct}%)",
                status="BLOCK",
            )
            # keep existing breakdown string expected by older tests
            line_state.add_breakdown(
                f"Minimummarge: BLOCK ({margin_pct}% < {min_pct}%)"
            )

            raise BlockQuote(
                "MARGIN_BLOCK",
                "Minimum margin not met.",
                {
                    "min_margin_pct": str(min_pct),
                    "margin_pct": str(margin_pct),
                    "cost": str(cost),
                    "sell": str(sell),
                    "productGroup": group,
                },
            )

        # Always visible check (OK)
        line_state.breakdown.add_check(
            "MIN_MARGIN_OK",
            f"Minimummarge: OK (≥{min_pct}%)",
            status="OK",
        )
        # keep backwards compatible string
        line_state.add_breakdown(f"Minimummarge check: OK (≥{min_pct}%)")

        return RuleResult.applied(
            D("0.00"),
            {"min_margin_pct": str(min_pct), "margin_pct": str(margin_pct)},
        )
