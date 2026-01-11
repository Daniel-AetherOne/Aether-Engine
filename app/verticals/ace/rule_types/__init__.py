# Ensure registration happens by importing modules
from .base import Rule, RuleResult, BlockQuote, rule_registry  # noqa
from . import (  # noqa
    min_margin,
    tier_discount,
    customer_discount,
    transport,
    net_cost,
    block,
    approval,
)
