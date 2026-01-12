from decimal import Decimal
import pytest
from dataclasses import replace

from app.verticals.ace.rule_types.net_cost import NetCostRule


def test_net_cost_happy(ctx, line_state):
    rule = NetCostRule(rule_id="net_cost_1", title="Net cost", params={})
    out = rule.apply(ctx=ctx, line_state=line_state)

    assert out.decision == "APPLIED"
    assert line_state.net_cost == Decimal("34.65")  # 10*3=30 *1.10=33 *1.05=34.65
    assert line_state.net_sell == Decimal("34.65")
    assert any("Netto inkoop" in s for s in line_state.breakdown)


def test_net_cost_edge_unknown_supplier_defaults_1(ctx, line_state):
    # ArticleSnapshot is frozen => replace it
    line_state.article = replace(line_state.article, supplier=None)
    ctx.data.tables["supplier_factors"] = {"SUP1": "1.10"}  # doesn't matter now
    ctx.data.tables["currency_markup_pct"] = {"EUR": "5"}

    rule = NetCostRule(rule_id="net_cost_1", title="Net cost", params={})
    rule.apply(ctx=ctx, line_state=line_state)

    # 10*3=30 *1.00=30 *1.05=31.50
    assert line_state.net_cost == Decimal("31.50")


def test_net_cost_invalid_missing_article(ctx, line_state):
    line_state.article = None

    rule = NetCostRule(rule_id="net_cost_1", title="Net cost", params={})
    out = rule.apply(ctx=ctx, line_state=line_state)

    assert out.decision == "SKIPPED"
    assert any("geen artikel" in s.lower() for s in line_state.breakdown)
