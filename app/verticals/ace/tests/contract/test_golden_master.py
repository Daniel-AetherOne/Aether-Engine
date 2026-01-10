import json
from pathlib import Path

import jsonschema

from engine.contract_reference import generate_quote_v1

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "schemas"
FIXTURES = ROOT / "tests" / "fixtures"


def _load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def test_golden_master_output_matches_exactly():
    input_payload = _load(FIXTURES / "input.v1.sample.json")
    output_schema = _load(SCHEMAS / "output.v1.schema.json")

    out = generate_quote_v1(input_payload)

    # Must satisfy schema
    jsonschema.validate(instance=out, schema=output_schema)

    golden_path = FIXTURES / "output.v1.golden.json"
    assert golden_path.exists(), "Create output.v1.golden.json once, then freeze it."

    golden = _load(golden_path)
    assert out == golden
