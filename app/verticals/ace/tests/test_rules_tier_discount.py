from decimal import Decimal

import app.verticals.ace.rule_types  # noqa
from app.verticals.ace.engine.rule_runner import RuleRunner, RuleSet
from app.verticals.ace.engine.context import QuoteInput, QuoteLineInput, ActiveData


def test_tier_discount_applies_highest_tier():
    ruleset = RuleSet.from_dict(
        {
            "version": "v1",
            "executionOrder": ["tier_1"],
            "rules": [
                {
                    "id": "tier_1",
                    "type": "tier_discount",
                    "title": "Tier",
                    "enabled": True,
                    "params": {},
                }
            ],
        }
    )
    runner = RuleRunner(ruleset)

    data = ActiveData(
        tables={
            "articles": {
                "SKU1": {"buyPrice": "10.00", "weightKg": "0.0", "productGroup": "A"}
            },
            "tiers": [
                {"min": 1, "max": 9, "pct": "0"},
                {"min": 10, "max": 24, "pct": "3"},
                {"min": 25, "pct": "5"},
            ],
        }
    )

    qin = QuoteInput(
        currency="EUR",
        lines=[QuoteLineInput(line_id="l1", sku="SKU1", qty=Decimal("25"))],
    )

    out = runner.run(qin=qin, data=data)

    assert out.status == "OK"
    # Quote-level breakdown should include rule id
    assert [b.rule_id for b in out.price_breakdown] == ["tier_1"]
