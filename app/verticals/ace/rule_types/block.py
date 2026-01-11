from __future__ import annotations

from .base import D, BlockQuote, Rule, RuleResult, register


@register
class BlockRule(Rule):
    """
    Handmatige block voor tests / feature flags.
    params:
      code: "SOME_CODE"
      message: "..."
    """
    type_name = "block"

    def apply(self, qin, data, state) -> RuleResult:
        raise BlockQuote(
            code=str(self.params.get("code", "BLOCKED")),
            message=str(self.params.get("message", "Blocked by rule.")),
            meta=dict(self.params.get("meta") or {}),
        )
