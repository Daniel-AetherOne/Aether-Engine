from __future__ import annotations

from .base import D, Rule, RuleResult, register
from ..calculators.net_cost import calc_net_cost


@register
class NetCostInfoRule(Rule):
    """
    Alleen info voor explainability (geen delta).
    """
    type_name = "net_cost_info"

    def apply(self, qin, data, state) -> RuleResult:
        net_cost = calc_net_cost(qin, data)
        return RuleResult(decision="APPLIED", delta=D("0.00"), meta={"net_cost": str(net_cost)})
