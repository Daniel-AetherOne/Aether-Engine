import json
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "schemas"


def _load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def test_input_schema_is_valid_jsonschema():
    schema = _load(SCHEMAS / "input.v1.schema.json")
    jsonschema.Draft202012Validator.check_schema(schema)


def test_output_schema_is_valid_jsonschema():
    schema = _load(SCHEMAS / "output.v1.schema.json")
    jsonschema.Draft202012Validator.check_schema(schema)


def test_error_schema_is_valid_jsonschema():
    schema = _load(SCHEMAS / "error.v1.schema.json")
    jsonschema.Draft202012Validator.check_schema(schema)
