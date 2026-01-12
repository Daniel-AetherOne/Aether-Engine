from __future__ import annotations

from .base import D, Rule, RuleResult, register


@register
class NetCostRule(Rule):
    """
    3.5.2 — Netto inkoopberekening (per line)

    Explain (FASE 4.3):
      - altijd 1 entry: NET_COST
    """

    type_name = "net_cost"

    def apply(self, ctx, line_state) -> RuleResult:
        if not line_state.article:
            # Policy A: NET_COST is "altijd" — maar zonder artikel kunnen we geen net_cost zetten.
            # We maken dit een META entry zodat het niet als price-step voelt.
            line_state.breakdown.add_meta(
                "NET_COST", "Netto inkoop: SKIP (geen artikel)"
            )
            return RuleResult.skipped({"reason": "no_article"})

        buy = line_state.article.buy_price
        qty = line_state.qty
        supplier = line_state.article.supplier
        currency = ctx.input.currency

        supplier_factors = (ctx.data.tables or {}).get("supplier_factors") or {}
        currency_markup = (ctx.data.tables or {}).get("currency_markup_pct") or {}

        factor = D(str(supplier_factors.get(supplier, "1.0"))) if supplier else D("1.0")
        markup_pct = D(str(currency_markup.get(currency, "0")))

        base = buy * qty
        with_factor = base * factor
        with_markup = with_factor * (D("1.0") + (markup_pct / D("100")))

        net_cost = with_markup.quantize(D("0.01"))

        line_state.net_cost = net_cost
        # baseline: start sell price from net cost (later discounts/transport/margin adjust)
        line_state.net_sell = net_cost

        # Policy A: 1 entry (altijd). Keep it stable + readable.
        line_state.breakdown.add_step(
            "NET_COST",
            f"Netto inkoop: {currency} {net_cost} (factor={factor}, opslag={markup_pct}%)",
        )

        return RuleResult.applied(
            D("0.00"),
            {
                "net_cost": str(net_cost),
                "factor": str(factor),
                "markup_pct": str(markup_pct),
            },
        )
