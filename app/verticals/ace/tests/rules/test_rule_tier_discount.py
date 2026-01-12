from decimal import Decimal

from app.verticals.ace.rule_types.tier_discount import TierDiscountRule


def test_tier_discount_happy_selects_10_24(ctx, line_state):
    line_state.qty = Decimal("10")
    rule = TierDiscountRule(rule_id="tier_discount_1", title="Tier", params={})
    out = rule.apply(ctx=ctx, line_state=line_state)

    assert out.decision in ("APPLIED", "SKIPPED")
    assert line_state.tier_discount_pct == Decimal("8")
    assert any("Staffel" in s for s in line_state.breakdown)


def test_tier_discount_edge_25_plus(ctx, line_state):
    line_state.qty = Decimal("25")
    rule = TierDiscountRule(rule_id="tier_discount_1", title="Tier", params={})
    rule.apply(ctx=ctx, line_state=line_state)

    assert line_state.tier_discount_pct == Decimal("12")


def test_tier_discount_invalid_no_tiers_table(ctx, line_state):
    ctx.data.tables["tiers"] = []
    rule = TierDiscountRule(rule_id="tier_discount_1", title="Tier", params={})
    rule.apply(ctx=ctx, line_state=line_state)

    assert line_state.tier_discount_pct == Decimal("0")
