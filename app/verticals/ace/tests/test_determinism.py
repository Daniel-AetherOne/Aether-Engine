from datetime import datetime, timezone
from decimal import Decimal

import app.verticals.ace.rule_types  # noqa
from app.verticals.ace.engine.quote_engine import QuoteEngine
from app.verticals.ace.engine.context import QuoteInput, QuoteLineInput, ActiveData


def test_determinism_same_input_same_output():
    engine = QuoteEngine.from_yaml_file("app/verticals/ace/rules/rule_sets/v1.yaml")

    data = ActiveData(
        tables={
            "articles": {
                "SKU1": {"buyPrice": "10.00", "weightKg": "2.0", "productGroup": "A"}
            },
            "postcode_zones": {"1234": "C"},
            "zone_rate_eur_per_kg": {"C": "0.00"},
            "customer_profile_discount_pct": {"B": "0"},
            "customer_max_extra_discount_pct": {"B": "0"},
            "min_margin_pct_by_group": {"A": "0"},
        }
    )

    qin = QuoteInput(
        currency="EUR",
        ship_to_postcode="1234AB",
        customer_segment="B",
        discount_percent=Decimal("0"),
        lines=[QuoteLineInput(line_id="l1", sku="SKU1", qty=Decimal("3"))],
    )

    fixed_now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    out1 = engine.calculate(qin, data, quote_id="test_quote_1", now=fixed_now)
    out2 = engine.calculate(qin, data, quote_id="test_quote_1", now=fixed_now)

    assert out1 == out2
