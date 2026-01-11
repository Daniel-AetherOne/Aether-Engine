from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Optional, Type, TYPE_CHECKING

D = Decimal

# Decisions (avoid string typos)
DECISION_APPLIED = "APPLIED"
DECISION_SKIPPED = "SKIPPED"

if TYPE_CHECKING:
    from ..engine.context import EngineContext, LineState


@dataclass(frozen=True)
class RuleResult:
    """
    Result of applying a rule.
    - decision: APPLIED / SKIPPED
    - delta: quote-level delta (MVP). Can be negative.
    - meta: explainability payload for breakdown.
    """

    decision: str
    delta: D
    meta: Dict[str, Any]

    @staticmethod
    def applied(delta: D, meta: Optional[Dict[str, Any]] = None) -> "RuleResult":
        return RuleResult(decision=DECISION_APPLIED, delta=delta, meta=meta or {})

    @staticmethod
    def skipped(meta: Optional[Dict[str, Any]] = None) -> "RuleResult":
        return RuleResult(decision=DECISION_SKIPPED, delta=D("0.00"), meta=meta or {})


class BlockQuote(Exception):
    """
    Raise this from a rule to block the quote deterministically.
    """

    def __init__(self, code: str, message: str, meta: Optional[Dict[str, Any]] = None):
        self.code = str(code)
        self.message = str(message)
        self.meta = meta or {}
        super().__init__(f"{self.code}: {self.message}")


class Rule:
    """
    Base class for all rules. Every rule must implement apply(ctx, line_state).

    ctx: EngineContext (input + active data + runtime + accumulators + quote state)
    line_state: LineState (per line mutable state; MVP uses first line as carrier)
    """

    type_name: str = "base"

    def __init__(self, rule_id: str, title: str, params: Dict[str, Any]):
        self.rule_id = str(rule_id)
        self.title = str(title)
        self.params = params or {}

    def apply(self, ctx: "EngineContext", line_state: "LineState") -> RuleResult:
        raise NotImplementedError


# Registry: rule_type -> Rule class
rule_registry: Dict[str, Type[Rule]] = {}


def register(rule_cls: Type[Rule]) -> Type[Rule]:
    """
    Decorator to register a rule by its type_name.
    Fails fast on duplicate registrations (useful during dev/reload).
    """
    key = getattr(rule_cls, "type_name", None)
    if not key:
        raise ValueError(f"Rule class {rule_cls.__name__} has no type_name")

    if key in rule_registry and rule_registry[key] is not rule_cls:
        raise ValueError(
            f"Duplicate rule registration for type '{key}': "
            f"{rule_registry[key].__name__} vs {rule_cls.__name__}"
        )

    rule_registry[key] = rule_cls
    return rule_cls
