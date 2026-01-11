from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Type

from .context import (
    ActiveData,
    EngineContext,
    LineState,
    PriceBreakdownLineV1,
    QuoteInput,
    QuoteOutputV1,
)
from ..rule_types.base import Rule, RuleResult, BlockQuote, rule_registry

D = Decimal


@dataclass(frozen=True)
class RuleSpec:
    id: str
    type: str
    title: str
    enabled: bool = True
    params: Dict[str, Any] | None = None

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "RuleSpec":
        return RuleSpec(
            id=str(d["id"]),
            type=str(d["type"]),
            title=str(d.get("title") or d["id"]),
            enabled=bool(d.get("enabled", True)),
            params=dict(d.get("params") or {}),
        )


@dataclass(frozen=True)
class RuleSet:
    rule_set_version: str
    execution_order: List[str]
    rules: List[RuleSpec]

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "RuleSet":
        rules = [RuleSpec.from_dict(x) for x in d.get("rules", [])]
        execution_order = list(d.get("executionOrder") or [])
        rule_set_version = str(d.get("ruleSetVersion") or d.get("version") or "v1")

        # Cross-validation (no runtime surprises)
        ids = [r.id for r in rules]

        if len(ids) != len(set(ids)):
            seen, dups = set(), []
            for rid in ids:
                if rid in seen and rid not in dups:
                    dups.append(rid)
                seen.add(rid)
            raise ValueError(f"Duplicate rule ids in ruleset: {dups}")

        if len(execution_order) != len(set(execution_order)):
            seen, dups = set(), []
            for rid in execution_order:
                if rid in seen and rid not in dups:
                    dups.append(rid)
                seen.add(rid)
            raise ValueError(f"Duplicate rule ids in executionOrder: {dups}")

        missing = sorted(set(execution_order) - set(ids))
        if missing:
            raise ValueError(f"executionOrder references unknown rule ids: {missing}")

        unlisted = sorted(set(ids) - set(execution_order))
        if unlisted:
            raise ValueError(f"Rules not listed in executionOrder: {unlisted}")

        if not execution_order:
            raise ValueError("executionOrder must contain at least one rule id.")

        return RuleSet(
            rule_set_version=rule_set_version,
            execution_order=execution_order,
            rules=rules,
        )


class RuleRunner:
    def __init__(self, ruleset: RuleSet):
        self.ruleset = ruleset

    def run(self, qin: QuoteInput, data: ActiveData) -> QuoteOutputV1:
        ctx = EngineContext(input=qin, data=data, contract_version="v1")

        rules_by_id: Dict[str, RuleSpec] = {r.id: r for r in self.ruleset.rules}

        # 3.2: lines (MVP: als leeg -> synthetic single line met base_amount)
        if qin.lines:
            line_states: List[LineState] = [
                LineState(line_id=l.line_id, subtotal=l.base_amount, meta=dict(l.meta))
                for l in qin.lines
            ]
        else:
            line_states = [
                LineState(line_id="line_1", subtotal=qin.base_amount, meta={})
            ]

        # MVP: we houden quote subtotal gelijk aan input base_amount en passen deltas toe op quote-level.
        # (Later kun je deltas per line boeken en daarna totaliseren.)
        for rule_id in self.ruleset.execution_order:
            spec = rules_by_id[rule_id]  # gegarandeerd door cross-validation

            if not spec.enabled:
                ctx.state.breakdown.append(
                    PriceBreakdownLineV1(
                        rule_id=spec.id,
                        rule_type=spec.type,
                        title=spec.title,
                        decision="SKIPPED",
                        delta=ctx.state.money(D("0.00")),
                        subtotal_after=ctx.state.money(ctx.state.subtotal),
                        meta={"reason": "disabled"},
                    )
                )
                continue

            rule_cls: Type[Rule] | None = rule_registry.get(spec.type)
            if rule_cls is None:
                ctx.blocking.append(
                    {
                        "code": "UNKNOWN_RULE_TYPE",
                        "ruleId": spec.id,
                        "ruleType": spec.type,
                        "message": f"Unknown rule type: {spec.type}",
                    }
                )
                ctx.state.breakdown.append(
                    PriceBreakdownLineV1(
                        rule_id=spec.id,
                        rule_type=spec.type,
                        title=spec.title,
                        decision="BLOCKED",
                        delta=ctx.state.money(D("0.00")),
                        subtotal_after=ctx.state.money(ctx.state.subtotal),
                        meta={"error": "unknown_rule_type"},
                    )
                )
                return QuoteOutputV1(
                    version="v1",
                    currency=ctx.state.currency,
                    status="BLOCKED",
                    total=ctx.state.money(ctx.state.subtotal),
                    price_breakdown=ctx.state.breakdown,
                    blocks=ctx.blocking,
                )

            rule = rule_cls(rule_id=spec.id, title=spec.title, params=spec.params or {})

            # MVP: rules draaien 1x op quote-level (met first line_state als “carrier”).
            # Later: per-line rules => loop over line_states.
            line_state = line_states[0]

            try:
                result: RuleResult = rule.apply(ctx=ctx, line_state=line_state)
            except BlockQuote as b:
                ctx.blocking.append(
                    {
                        "code": b.code,
                        "ruleId": spec.id,
                        "ruleType": spec.type,
                        "message": b.message,
                        "meta": b.meta,
                    }
                )
                ctx.state.breakdown.append(
                    PriceBreakdownLineV1(
                        rule_id=spec.id,
                        rule_type=spec.type,
                        title=spec.title,
                        decision="BLOCKED",
                        delta=ctx.state.money(D("0.00")),
                        subtotal_after=ctx.state.money(ctx.state.subtotal),
                        meta=b.meta,
                    )
                )
                return QuoteOutputV1(
                    version="v1",
                    currency=ctx.state.currency,
                    status="BLOCKED",
                    total=ctx.state.money(ctx.state.subtotal),
                    price_breakdown=ctx.state.breakdown,
                    blocks=ctx.blocking,
                )

            # Apply delta to quote subtotal
            ctx.state.subtotal += result.delta
            ctx.state.breakdown.append(
                PriceBreakdownLineV1(
                    rule_id=spec.id,
                    rule_type=spec.type,
                    title=spec.title,
                    decision=result.decision,
                    delta=ctx.state.money(result.delta),
                    subtotal_after=ctx.state.money(ctx.state.subtotal),
                    meta=result.meta,
                )
            )

        return QuoteOutputV1(
            version="v1",
            currency=ctx.state.currency,
            status="OK",
            total=ctx.state.money(ctx.state.subtotal),
            price_breakdown=ctx.state.breakdown,
            blocks=ctx.blocking,
        )
