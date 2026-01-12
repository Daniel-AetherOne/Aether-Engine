from __future__ import annotations

from .base import D, Rule, RuleResult, register


@register
class TierDiscountRule(Rule):
    type_name = "tier_discount"

    def apply(self, ctx, line_state) -> RuleResult:
        tiers = (ctx.data.tables or {}).get("tiers")
        if not tiers or not isinstance(tiers, list):
            return RuleResult.skipped({"reason": "missing_or_invalid_tiers_table"})

        qty = line_state.qty
        if qty is None:
            return RuleResult.skipped({"reason": "missing_qty"})

        best = None
        best_min = None

        for t in tiers:
            try:
                tmin = D(str(t.get("min")))
            except Exception:
                continue

            tmax_raw = t.get("max", None)
            tmax = None
            if tmax_raw is not None:
                try:
                    tmax = D(str(tmax_raw))
                except Exception:
                    tmax = None

            if qty < tmin:
                continue
            if tmax is not None and qty > tmax:
                continue

            if best is None or (best_min is not None and tmin > best_min):
                best = t
                best_min = tmin

        if best is None:
            line_state.tier_discount_pct = D("0.00")
            return RuleResult.skipped({"reason": "no_matching_tier", "qty": str(qty)})

        pct = D(str(best.get("pct", "0"))).quantize(D("0.01"))
        line_state.tier_discount_pct = pct

        # ✅ test expects "Staffel" somewhere in breakdown
        line_state.add_breakdown(f"Staffel korting: {pct}% (qty={qty})")

        # FASE 4: selector-only explain (delta 0) via Breakdown meta
        # (kept as meta so Policy A can decide to show/hide later)
        line_state.breakdown.add_meta(
            "TIER_DISCOUNT",
            f"{self.title}: {pct}%",
        )

        # ✅ selector-only: keep quote-level breakdown stable (does not change totals)
        return RuleResult.applied(D("0.00"), {"pct": str(pct), "qty": str(qty)})
