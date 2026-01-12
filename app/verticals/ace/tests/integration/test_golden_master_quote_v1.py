from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from decimal import Decimal
from datetime import datetime


def _normalize(obj):
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _normalize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize(x) for x in obj]
    return obj


def test_golden_master_quote_v1(sample_engine, sample_data_ok, sample_qin, fixed_now):
    out = sample_engine.calculate(
        sample_qin, sample_data_ok, quote_id="test_quote_1", now=fixed_now
    )
    payload = _normalize(asdict(out))

    golden_path = Path("app/verticals/ace/tests/golden/quote_v1.json")

    if (not golden_path.exists()) or (golden_path.stat().st_size == 0):
        golden_path.parent.mkdir(parents=True, exist_ok=True)
        golden_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
        )
        assert (
            False
        ), "Golden master created (or repaired). Commit the file and rerun tests."

    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    assert payload == golden
