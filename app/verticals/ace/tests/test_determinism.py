from decimal import Decimal

from app.verticals.ace.engine.quote_engine import QuoteEngine
from app.verticals.ace.engine.context import QuoteInput, ActiveData

D = Decimal


def test_determinism_same_input_same_output():
    engine = QuoteEngine.from_yaml_file("app/verticals/ace/rules/rule_sets/v1.yaml")

    qin = QuoteInput(
        currency="EUR",
        base_amount=D("2000.00"),
        material_cost=D("700.00"),
        labor_cost=D("500.00"),
        transport_km=D("10"),
        discount_percent=D("5"),
    )
    data = ActiveData(tables={})

    out1 = engine.calculate(qin, data)
    out2 = engine.calculate(qin, data)

    assert out1 == out2
    assert out1.version == "v1"
    assert out1.currency == "EUR"
    assert len(out1.price_breakdown) > 0
