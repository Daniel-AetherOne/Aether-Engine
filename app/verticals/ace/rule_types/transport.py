from __future__ import annotations

from .base import D, Rule, RuleResult, register


@register
class TransportRule(Rule):
    """
    3.5.3 — Transport toeslag (per line)

    Explain (FASE 4.3):
      - 1 entry alleen als cost > 0: TRANSPORT
      - warnings blijven via ctx.warn
    """

    type_name = "transport"

    def apply(self, ctx, line_state) -> RuleResult:
        if not line_state.article:
            # transport zonder artikel is niet berekenbaar -> meta (geen price step)
            line_state.breakdown.add_meta("TRANSPORT", "Transport: SKIP (geen artikel)")
            return RuleResult.skipped({"reason": "no_article"})

        postcode = (ctx.input.ship_to_postcode or "").strip().upper()
        if not postcode:
            ctx.warn(
                "POSTCODE_MISSING", "No ship_to_postcode provided; transport set to 0."
            )
            line_state.transport_cost = D("0.00")
            # Policy A: bij 0 tonen we geen step
            return RuleResult.skipped({"reason": "postcode_missing"})

        zones = (ctx.data.tables or {}).get("postcode_zones") or {}
        rates = (ctx.data.tables or {}).get("zone_rate_eur_per_kg") or {}

        # MVP: try prefixes 4->2
        zone = None
        for n in (4, 3, 2):
            key = postcode[:n]
            if key in zones:
                zone = str(zones[key])
                break

        if zone is None:
            ctx.warn(
                "POSTCODE_UNKNOWN",
                f"Unknown postcode zone for: {postcode}; transport set to 0.",
                postcode=postcode,
            )
            line_state.transport_cost = D("0.00")
            # Policy A: bij 0 tonen we geen step
            return RuleResult.skipped(
                {"reason": "postcode_unknown", "postcode": postcode}
            )

        rate = D(str(rates.get(zone, "0")))
        kg = (line_state.article.weight_kg * line_state.qty).quantize(D("0.001"))
        cost = (kg * rate).quantize(D("0.01"))

        line_state.transport_cost = cost
        line_state.net_sell = (line_state.net_sell + cost).quantize(D("0.01"))

        # Policy A: alleen tonen als effect > 0
        if cost > D("0.00"):
            line_state.breakdown.add_step(
                "TRANSPORT",
                f"Transport zone {zone}: +{cost} ({kg} kg × {rate}/kg)",
            )

        return RuleResult.applied(
            D("0.00"),
            {"zone": zone, "rate": str(rate), "kg": str(kg), "cost": str(cost)},
        )
