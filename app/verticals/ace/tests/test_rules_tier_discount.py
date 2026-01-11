from decimal import Decimal

from app.verticals.ace.engine.rule_runner import RuleRunner, RuleSet
from app.verticals.ace.engine.context import QuoteInput, ActiveData

# Important: ensure rule types are registered
import app.verticals.ace.rule_types  # noqa

D = Decimal


def test_tier_discount_applies_highest_tier():
    ruleset = RuleSet.from_dict(
        {
            "version": "v1",
            "rules": [
                {
                    "id": "tier_1",
                    "type": "tier_discount",
                    "title": "Tier",
                    "enabled": True,
                    "params": {
                        "tiers": [
                            {"min": "0", "percent": "0"},
                            {"min": "1000", "percent": "3"},
                            {"min": "2500", "percent": "5"},
                        ]
                    },
                }
            ],
        }
    )
    runner = RuleRunner(ruleset)

    qin = QuoteInput(currency="EUR", base_amount=D("2600.00"))
    out = runner.run(qin=qin, data=ActiveData())

    assert out.status == "OK"
    assert out.total.amount == D("2470.00")  # 5% korting op 2600 = 130
    assert out.price_breakdown[0].meta["pct"] == "5"
