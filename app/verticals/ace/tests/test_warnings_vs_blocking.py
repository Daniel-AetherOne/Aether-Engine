from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from app.verticals.ace.engine.quote_engine import QuoteEngine
from app.verticals.ace.engine.context import ActiveData, QuoteInput, QuoteLineInput


def test_warnings_and_blocks_are_separate():
    engine = QuoteEngine.from_yaml_file("app/verticals/ace/rules/rule_sets/v1.yaml")

    data = ActiveData(
        tables={
            "articles": {
                "SKU1": {
                    "buyPrice": "10.00",
                    "weightKg": "2.0",
                    "supplier": "SUP1",
                    "productGroup": "A",
                }
            },
            # Force postcode warning:
            "postcode_zones": {},  # unknown postcode => warn + transport 0
            "zone_rate_eur_per_kg": {},
            "customer_profile_discount_pct": {"B": "0"},
            "customer_max_extra_discount_pct": {"B": "0"},
            "min_margin_pct_by_group": {"A": "0"},
        }
    )

    qin = QuoteInput(
        currency="EUR",
        ship_to_postcode="9999ZZ",
        customer_segment="B",
        discount_percent=Decimal("0"),
        lines=[QuoteLineInput(line_id="l1", sku="SKU1", qty=Decimal("3"))],
    )

    out = engine.calculate(
        qin,
        data,
        quote_id="warn_block_sep",
        now=datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
    )

    assert isinstance(out.warnings, list)
    assert isinstance(out.blocks, list)

    warning_codes = {w.get("code") for w in out.warnings}
    block_codes = {b.get("code") for b in out.blocks}

    # In dit scenario verwachten we een postcode warning (of missing/unknown)
    assert ("POSTCODE_UNKNOWN" in warning_codes) or (
        "POSTCODE_MISSING" in warning_codes
    )

    # En diezelfde codes mogen nooit in blocks zitten
    assert "POSTCODE_UNKNOWN" not in block_codes
    assert "POSTCODE_MISSING" not in block_codes
