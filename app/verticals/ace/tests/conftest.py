from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

import app.verticals.ace.rule_types  # noqa: F401 (register all rules)

from app.verticals.ace.engine.context import ActiveData, QuoteInput, QuoteLineInput
from app.verticals.ace.engine.quote_engine import QuoteEngine
from app.verticals.ace.engine.rule_runner import RuleRunner, RuleSet
from app.verticals.ace.engine.line_state import LineState, ArticleSnapshot
from app.verticals.ace.engine.context import EngineContext


@pytest.fixture
def fixed_now():
    return datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def sample_data_ok():
    return ActiveData(
        tables={
            "articles": {
                "SKU1": {"buyPrice": "10.00", "weightKg": "2.0", "supplier": "SUP1", "productGroup": "A"},
            },
            "supplier_factors": {"SUP1": "1.10"},
            "currency_markup_pct": {"EUR": "5"},
            "tiers": [
                {"min": 1, "max": 9, "pct": "0"},
                {"min": 10, "max": 24, "pct": "8"},
                {"min": 25, "pct": "12"},
            ],
            "postcode_zones": {"1234": "C"},
            "zone_rate_eur_per_kg": {"C": "0.00"},
            "customer_profile_discount_pct": {"B": "2"},
            "customer_max_extra_discount_pct": {"B": "2"},
            "min_margin_pct_by_group": {"A": "0"},
        }
    )


@pytest.fixture
def sample_qin():
    return QuoteInput(
        currency="EUR",
        ship_to_postcode="1234AB",
        customer_segment="B",
        discount_percent=Decimal("0"),
        lines=[QuoteLineInput(line_id="l1", sku="SKU1", qty=Decimal("3"))],
    )


@pytest.fixture
def sample_engine():
    # Uses your real YAML ruleset (also validates executionOrder)
    return QuoteEngine.from_yaml_file("app/verticals/ace/rules/rule_sets/v1.yaml")


@pytest.fixture
def ctx(sample_qin, sample_data_ok, fixed_now):
    # Minimal ctx for unit-testing rules directly
    return EngineContext(
        input=sample_qin,
        data=sample_data_ok,
        contract_version="v1",
        quote_id="test_quote_1",
        now=fixed_now,
    )


@pytest.fixture
def line_state():
    # Minimal line state for unit tests; rule-specific tests can override fields
    return LineState(
        line_id="l1",
        sku="SKU1",
        qty=Decimal("3"),
        article=ArticleSnapshot(
            sku="SKU1",
            buy_price=Decimal("10.00"),
            weight_kg=Decimal("2.0"),
            supplier="SUP1",
            product_group="A",
        ),
        meta={},
    )
