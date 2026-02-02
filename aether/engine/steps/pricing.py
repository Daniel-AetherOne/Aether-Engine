# aether/engine/steps/pricing.py
from __future__ import annotations
from aether.engine.context import PipelineState, StepResult
from aether.engine.config import StepConfig

def pricing_rules_v1(state: PipelineState, step: StepConfig, assets: dict) -> StepResult:
    rules = assets["rules"]  # already-loaded dict
    agg = state.data.get("steps", {}).get("aggregate", {})
    if not agg:
        return StepResult(status="FAILED", error="Missing aggregate output")

    # TODO: call your existing pricing_engine_us but make it generic via rules
    # price_out = pricing_engine.apply(rules, agg, params=step.with_)
    price_out = {"total": 0, "line_items": [], "currency": step.with_.get("currency", "USD")}

    # TODO: call needs_review_from_output equivalent (generic rule check)
    # if needs_review(price_out, rules): ...
    return StepResult(status="OK", data=price_out)
