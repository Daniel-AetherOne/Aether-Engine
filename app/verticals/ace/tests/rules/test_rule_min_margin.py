from decimal import Decimal
import pytest

from app.verticals.ace.rule_types.min_margin import MinMarginRule
from app.verticals.ace.rule_types.base import BlockQuote


def test_min_margin_happy_ok(ctx, line_state):
    ctx.data.tables["min_margin_pct_by_group"]["A"] = "0"

    line_state.net_cost = Decimal("30.00")
    line_state.transport_cost = Decimal("0.00")
    line_state.net_sell = Decimal("30.00")

    rule = MinMarginRule(rule_id="min_margin_1", title="Min margin", params={})
    out = rule.apply(ctx=ctx, line_state=line_state)

    assert out.decision == "APPLIED"
    assert line_state.margin_pct == Decimal("0.00")


def test_min_margin_edge_blocks_negative_margin(ctx, line_state):
    ctx.data.tables["min_margin_pct_by_group"]["A"] = "0"

    line_state.net_cost = Decimal("32.10")
    line_state.transport_cost = Decimal("0.00")
    line_state.net_sell = Decimal("31.14")  # negative margin

    rule = MinMarginRule(rule_id="min_margin_1", title="Min margin", params={})
    with pytest.raises(BlockQuote):
        rule.apply(ctx=ctx, line_state=line_state)


def test_min_margin_invalid_sell_zero_blocks(ctx, line_state):
    line_state.net_cost = Decimal("1.00")
    line_state.transport_cost = Decimal("0.00")
    line_state.net_sell = Decimal("0.00")

    rule = MinMarginRule(rule_id="min_margin_1", title="Min margin", params={})
    with pytest.raises(BlockQuote):
        rule.apply(ctx=ctx, line_state=line_state)
