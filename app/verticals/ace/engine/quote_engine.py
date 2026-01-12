from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from datetime import datetime

from .context import ActiveData, QuoteInput, QuoteOutputV1
from .rule_loader import RuleLoader


@dataclass
class QuoteEngine:
    """
    3.7 — QuoteEngine with hot-reloadable ruleset.
    """

    rule_loader: RuleLoader

    @staticmethod
    def from_yaml_file(path: str) -> "QuoteEngine":
        return QuoteEngine(rule_loader=RuleLoader(path))

    def calculate(
        self, qin, data=None, *, quote_id="quote_1", now: Optional[datetime] = None
    ):
        loaded = self.rule_loader.get()
        return loaded.runner.run(qin=qin, data=data, quote_id=quote_id, now=now)
