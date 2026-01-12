from datetime import datetime, timezone

def test_integration_quote_end_to_end(sample_engine, sample_data_ok, sample_qin, fixed_now):
    out = sample_engine.calculate(sample_qin, sample_data_ok, quote_id="test_quote_1", now=fixed_now)

    assert out.price_breakdown is not None
    assert len(out.price_breakdown) >= 1
    assert out.total.amount is not None
