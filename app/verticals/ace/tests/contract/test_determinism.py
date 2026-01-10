import json
from pathlib import Path

from engine.contract_reference import generate_quote_v1

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures"


def test_determinism_same_input_same_output():
    input_payload = json.loads((FIXTURES / "input.v1.sample.json").read_text(encoding="utf-8"))

    out1 = generate_quote_v1(input_payload)
    out2 = generate_quote_v1(input_payload)
    out3 = generate_quote_v1(input_payload)

    assert out1 == out2 == out3
