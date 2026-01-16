from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Type

from app.verticals.ace.explain.breakdown_builder import BreakdownBuilder

from .context import (
    ActiveData,
    EngineContext,
    PriceBreakdownLineV1,
    QuoteInput,
    QuoteLineOutputV1,
    QuoteOutputV1,
)
from .line_state import LineState, load_article_snapshot
from ..rule_types.base import BlockQuote, Rule, RuleResult, rule_registry

D = Decimal


# -----------------------
# Ruleset models (3.1+)
# -----------------------


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

        # Cross-validation
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


# -----------------------
# Runner
# -----------------------


class RuleRunner:
    """
    3.4 — Deterministic rule runner.

    3.8 additions:
    - `now` is injected (no datetime.now() usage in rules; only here as fallback)
    - `quote_id` is injected/controlled by caller

    Behavior:
    - line-by-line (no cross-line optimization)
    - for rule in executionOrder: apply rule to each line (ctx, line_state)
    - rule may mutate line_state, add warnings, add blocking
    - on blocking: return BLOCKED quote with ctx.blocking filled
    """

    def __init__(self, ruleset: RuleSet):
        self.ruleset = ruleset

    def _build_lines(self, ctx: EngineContext) -> List[LineState]:
        qin = ctx.input

        if not qin.lines:
            ctx.block("NO_LINES", "No quote lines provided.")
            return []

        line_states: List[LineState] = []
        for l in qin.lines:
            sku = str(l.sku)
            qty = D(str(l.qty))

            snap = load_article_snapshot(ctx.data.tables, sku)
            if snap is None:
                # MVP: Missing SKU => BLOCK
                ctx.block(
                    "MISSING_SKU",
                    f"SKU not found in active dataset: {sku}",
                    sku=sku,
                    lineId=l.line_id,
                )

                ls = LineState(
                    line_id=l.line_id,
                    sku=sku,
                    qty=qty,
                    meta=dict(getattr(l, "meta", {}) or {}),
                )
                # Explain (per line)
                ls.breakdown.add_check(
                    "MISSING_SKU", f"SKU ontbreekt: {sku}", status="BLOCK"
                )
                line_states.append(ls)
                continue

            ls = LineState(
                line_id=l.line_id,
                sku=sku,
                qty=qty,
                article=snap,
                meta=dict(getattr(l, "meta", {}) or {}),
            )
            ls.breakdown.add_meta(
                "INIT", f"sku={sku}, qty={qty}, buyPrice={snap.buy_price}"
            )
            line_states.append(ls)

        return line_states

    @staticmethod
    def _recompute_total(lines: List[LineState]) -> D:
        total = D("0.00")
        for ls in lines:
            total += ls.net_sell
        return total.quantize(D("0.01"))

    @staticmethod
    def _line_money_before(ls: LineState) -> D:
        """
        Deterministisch snapshot-punt per line om delta's te meten.
        We gebruiken net_sell omdat _recompute_total daarop gebaseerd is.
        """
        try:
            return D(str(ls.net_sell))
        except Exception:
            return D("0.00")

    @staticmethod
    def _code_from_rule_id(rule_id: str) -> str:
        """
        Zorgt dat we voldoen aan BreakdownBuilder's code regex (UPPER_SNAKE).
        """
        return str(rule_id).strip().upper().replace("-", "_").replace(" ", "_")

    def _finalize_line_steps(self, line_states: List[LineState]) -> None:
        """
        Build output strings for each line from its Breakdown.
        Store on LineState as `steps` so callers can map to output.
        """
        builder = BreakdownBuilder()
        for ls in line_states:
            steps = builder.build(ls.breakdown)
            # Prefer a real field if you add it; otherwise safe setattr.
            try:
                ls.steps = steps  # type: ignore[attr-defined]
            except Exception:
                setattr(ls, "steps", steps)

    def _build_output_lines(
        self, ctx: EngineContext, line_states: List[LineState]
    ) -> List[QuoteLineOutputV1]:
        out: List[QuoteLineOutputV1] = []
        for ls in line_states:
            steps = getattr(ls, "steps", [])
            out.append(
                QuoteLineOutputV1(
                    line_id=ls.line_id,
                    sku=ls.sku,
                    qty=ls.qty,
                    net_sell=ctx.state.money(ls.net_sell),
                    steps=list(steps),
                    meta=dict(getattr(ls, "meta", {}) or {}),
                )
            )
        return out

    def run(
        self,
        qin: QuoteInput,
        data: ActiveData,
        *,
        quote_id: str = "quote_1",
        now: Optional[datetime] = None,
    ) -> QuoteOutputV1:
        """
        3.8 deterministic entrypoint:
        - pass a fixed `now` and `quote_id` in tests
        """
        if now is None:
            now = datetime.now(timezone.utc)

        ctx = EngineContext(
            input=qin,
            data=data,
            contract_version="v1",
            quote_id=quote_id,
            now=now,
        )

        # Build lines (deterministic)
        line_states = self._build_lines(ctx)

        # BLOCK during build_lines (e.g. missing sku)
        if ctx.blocking:
            self._finalize_line_steps(line_states)
            ctx.state.subtotal = self._recompute_total(line_states)

            return QuoteOutputV1(
                version="v1",
                currency=ctx.state.currency,
                status="BLOCKED",
                total=ctx.state.money(ctx.state.subtotal),
                approval_required=bool(ctx.state.approval_required),
                approval_status=ctx.state.approval_status,
                price_breakdown=ctx.state.breakdown,
                lines=self._build_output_lines(ctx, line_states),
                blocks=ctx.blocking,
                warnings=ctx.warnings,
            )

        rules_by_id: Dict[str, RuleSpec] = {r.id: r for r in self.ruleset.rules}

        # Initialize total (usually 0 until first pricing rule sets net_sell)
        ctx.state.subtotal = self._recompute_total(line_states)

        for rule_index, rule_id in enumerate(self.ruleset.execution_order):
            spec = rules_by_id[rule_id]

            if not spec.enabled:
                ctx.state.breakdown.append(
                    PriceBreakdownLineV1(
                        rule_id=spec.id,
                        rule_type=spec.type,
                        title=spec.title,
                        decision="SKIPPED",
                        delta=ctx.state.money(D("0.00")),
                        subtotal_after=ctx.state.money(ctx.state.subtotal),
                        meta={"reason": "disabled", "mode": "per_line"},
                    )
                )
                # (MVP) geen per-line explain voor disabled rules
                continue

            rule_cls: Optional[Type[Rule]] = rule_registry.get(spec.type)
            if rule_cls is None:
                ctx.blocking.append(
                    {
                        "code": "UNKNOWN_RULE_TYPE",
                        "message": f"Unknown rule type: {spec.type}",
                        "meta": {"ruleId": spec.id, "ruleType": spec.type},
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
                        meta={"error": "unknown_rule_type", "mode": "per_line"},
                    )
                )

                self._finalize_line_steps(line_states)
                return QuoteOutputV1(
                    version="v1",
                    currency=ctx.state.currency,
                    status="BLOCKED",
                    total=ctx.state.money(ctx.state.subtotal),
                    approval_required=bool(ctx.state.approval_required),
                    approval_status=ctx.state.approval_status,
                    price_breakdown=ctx.state.breakdown,
                    lines=self._build_output_lines(ctx, line_states),
                    blocks=ctx.blocking,
                    warnings=ctx.warnings,
                )

            rule = rule_cls(rule_id=spec.id, title=spec.title, params=spec.params or {})

            # FASE 4.x: inject execution order index for explain ordering (optional use in rules)
            setattr(rule, "_execution_order", rule_index)

            before_total = ctx.state.subtotal
            applied_any = False

            # We meten per-line delta en loggen alleen steps met effect (delta != 0)
            for ls in line_states:
                before_line = self._line_money_before(ls)

                try:
                    result: RuleResult = rule.apply(ctx=ctx, line_state=ls)
                except BlockQuote as b:
                    ctx.blocking.append(
                        {
                            "code": b.code,
                            "message": b.message,
                            "meta": {
                                **b.meta,
                                "ruleId": spec.id,
                                "ruleType": spec.type,
                                "lineId": ls.line_id,
                                "sku": ls.sku,
                            },
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
                            meta={
                                "mode": "per_line",
                                "lineId": ls.line_id,
                                "sku": ls.sku,
                                **b.meta,
                            },
                        )
                    )

                    # Per-line explain: laat de blokkade altijd zien
                    ls.breakdown.add_check(
                        self._code_from_rule_id(spec.id),
                        f"{spec.title}: {b.message}",
                        status="BLOCK",
                    )

                    self._finalize_line_steps(line_states)
                    ctx.state.subtotal = self._recompute_total(line_states)

                    return QuoteOutputV1(
                        version="v1",
                        currency=ctx.state.currency,
                        status="BLOCKED",
                        total=ctx.state.money(ctx.state.subtotal),
                        approval_required=bool(ctx.state.approval_required),
                        approval_status=ctx.state.approval_status,
                        price_breakdown=ctx.state.breakdown,
                        lines=self._build_output_lines(ctx, line_states),
                        blocks=ctx.blocking,
                        warnings=ctx.warnings,
                    )

                # --- 6.3: hoist rule meta -> quote-level approval flag ---
                meta = getattr(result, "meta", None) or {}
                if meta.get("approval_required") is True:
                    ctx.state.approval_required = True

                if result.decision == "APPLIED":
                    applied_any = True

                after_line = self._line_money_before(ls)
                delta_line = (after_line - before_line).quantize(D("0.01"))

                # MVP Policy A: alleen steps met effect
                if delta_line != D("0.00"):
                    code = self._code_from_rule_id(spec.id)
                    # Houd message clean voor exports (geen tabs/newlines)
                    ls.breakdown.add_step(
                        code,
                        f"{spec.title}: {delta_line:+.2f}",
                    )

            ctx.state.subtotal = self._recompute_total(line_states)
            delta_total = (ctx.state.subtotal - before_total).quantize(D("0.01"))

            ctx.state.breakdown.append(
                PriceBreakdownLineV1(
                    rule_id=spec.id,
                    rule_type=spec.type,
                    title=spec.title,
                    decision="APPLIED" if applied_any else "SKIPPED",
                    delta=ctx.state.money(delta_total),
                    subtotal_after=ctx.state.money(ctx.state.subtotal),
                    meta={"mode": "per_line", "lines": len(line_states)},
                )
            )

        # Build per-line string outputs (single source of truth for consumers)
        self._finalize_line_steps(line_states)

        return QuoteOutputV1(
            version="v1",
            currency=ctx.state.currency,
            status="OK",
            total=ctx.state.money(ctx.state.subtotal),
            approval_required=bool(ctx.state.approval_required),
            approval_status=ctx.state.approval_status,
            price_breakdown=ctx.state.breakdown,
            lines=self._build_output_lines(ctx, line_states),
            blocks=ctx.blocking,
            warnings=ctx.warnings,
        )
