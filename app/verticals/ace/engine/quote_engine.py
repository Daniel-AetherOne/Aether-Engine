from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import yaml
from jsonschema import validate

from .context import ActiveData, QuoteInput, QuoteOutputV1
from .rule_runner import RuleRunner, RuleSet


class QuoteEngine:
    def __init__(self, ruleset_dict: Dict[str, Any]):
        self.ruleset = RuleSet.from_dict(ruleset_dict)
        self.runner = RuleRunner(self.ruleset)

    @classmethod
    def from_yaml_file(cls, path: str) -> "QuoteEngine":
        ruleset_path = Path(path)

        with ruleset_path.open("r", encoding="utf-8") as f:
            d = yaml.safe_load(f)

        schema_path = ruleset_path.parents[1] / "schemas" / "rule_set.schema.json"
        with schema_path.open("r", encoding="utf-8") as f:
            schema = json.load(f)

        validate(instance=d, schema=schema)
        return cls(d)

    def calculate(self, qin: QuoteInput, active_data: ActiveData) -> QuoteOutputV1:
        return self.runner.run(qin=qin, data=active_data)
