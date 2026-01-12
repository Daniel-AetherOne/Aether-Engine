from decimal import Decimal

from app.verticals.ace.rule_types.customer_discount import CustomerDiscountRule


def test_customer_discount_happy_profile_only(ctx, line_state):
    ctx.input.customer_segment = "B"
    ctx.input.discount_percent = Decimal("0")
    line_state.net_sell = Decimal("100.00")

    rule = CustomerDiscountRule(
        rule_id="customer_discount_1", title="Cust disc", params={}
    )
    out = rule.apply(ctx=ctx, line_state=line_state)

    assert out.decision == "APPLIED"
    # profile B=2%
    assert line_state.customer_discount_pct == Decimal("2.00")
    assert line_state.net_sell == Decimal("98.00")


def test_customer_discount_edge_cap(ctx, line_state):
    ctx.input.customer_segment = "B"
    ctx.input.discount_percent = Decimal("10")  # requested extra too high
    line_state.net_sell = Decimal("100.00")

    rule = CustomerDiscountRule(
        rule_id="customer_discount_1", title="Cust disc", params={}
    )
    rule.apply(ctx=ctx, line_state=line_state)

    # profile 2 + extra capped to 2 => 4%
    assert line_state.customer_discount_pct == Decimal("4.00")
    assert line_state.net_sell == Decimal("96.00")
    assert any(w["code"] == "DISCOUNT_CAPPED" for w in ctx.warnings)


def test_customer_discount_invalid_no_segment_defaults(ctx, line_state):
    ctx.input.customer_segment = None
    ctx.input.discount_percent = Decimal("0")
    line_state.net_sell = Decimal("100.00")

    rule = CustomerDiscountRule(
        rule_id="customer_discount_1", title="Cust disc", params={}
    )
    rule.apply(ctx=ctx, line_state=line_state)

    assert line_state.net_sell == Decimal("100.00")
