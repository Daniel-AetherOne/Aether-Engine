from decimal import Decimal

from app.verticals.ace.rule_types.transport import TransportRule


def test_transport_happy(ctx, line_state):
    # enable nonzero rate
    ctx.data.tables["zone_rate_eur_per_kg"]["C"] = "0.35"
    ctx.input.ship_to_postcode = "1234AB"

    # assume net_sell already set by net_cost
    line_state.net_sell = Decimal("30.00")

    rule = TransportRule(rule_id="transport_1", title="Transport", params={})
    out = rule.apply(ctx=ctx, line_state=line_state)

    assert out.decision == "APPLIED"
    # kg = 2.0*3=6, cost=6*0.35=2.10
    assert line_state.transport_cost == Decimal("2.10")
    assert line_state.net_sell == Decimal("32.10")


def test_transport_edge_unknown_postcode_warns(ctx, line_state):
    ctx.input.ship_to_postcode = "9999ZZ"
    line_state.net_sell = Decimal("30.00")

    rule = TransportRule(rule_id="transport_1", title="Transport", params={})
    out = rule.apply(ctx=ctx, line_state=line_state)

    assert out.decision == "SKIPPED"
    assert line_state.transport_cost == Decimal("0.00")
    assert any(w["code"] == "POSTCODE_UNKNOWN" for w in ctx.warnings)


def test_transport_invalid_missing_postcode(ctx, line_state):
    ctx.input.ship_to_postcode = ""
    line_state.net_sell = Decimal("30.00")

    rule = TransportRule(rule_id="transport_1", title="Transport", params={})
    out = rule.apply(ctx=ctx, line_state=line_state)

    assert out.decision == "SKIPPED"
    assert any(w["code"] == "POSTCODE_MISSING" for w in ctx.warnings)
