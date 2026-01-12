from __future__ import annotations

from .base import BlockQuote, Rule, RuleResult, register


@register
class BlockCountryRule(Rule):
    type_name = "block_country"

    def apply(self, ctx, line_state) -> RuleResult:
        country = (ctx.input.country or "").upper().strip()
        blocked = set(((ctx.data.tables or {}).get("blocked_countries") or []))
        if country and country in blocked:
            line_state.add_breakdown(f"BLOCK: land {country} niet toegestaan")
            raise BlockQuote("COUNTRY_BLOCK", "Country is blocked for selling.", {"country": country})
        return RuleResult.skipped({"country": country})
