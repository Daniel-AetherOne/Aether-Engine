from __future__ import annotations

from .base import D, Rule, RuleResult, register


@register
class ApprovalRule(Rule):
    """
    Placeholder: in MVP doen we nog niets (geen async/approval flow).
    """
    type_name = "approval"

    def apply(self, qin, data, state) -> RuleResult:
        return RuleResult(decision="SKIPPED", delta=D("0.00"), meta={"reason": "not_implemented"})
