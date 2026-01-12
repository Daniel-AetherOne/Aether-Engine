# app/verticals/ace/explain/explain_models.py
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence


@dataclass(frozen=True)
class ExplainEntry:
    """
    Eén stap in de opbouw, toegevoegd door een rule.
    - order: rule executionOrder (bepaalt volgorde)
    - seq: stabiele increment binnen dezelfde order (bepaalt determinisme)
    - kind: 'BASE', 'PCT', 'TRANSPORT', 'MIN_MARGIN', 'NOTE', ...
    - label: korte naam (UI/Excel/mail)
    - delta: effect op prijs (kan 0 zijn voor 'always show' stappen zoals basis)
    - meta: rule-specifieke details (optioneel, voor debug/inspect)
    """

    order: int
    seq: int
    kind: str
    label: str
    delta: Decimal
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def has_effect(self) -> bool:
        return self.delta != Decimal("0")


@dataclass
class LineExplain:
    """
    Explain entries per line (één offertregel).
    """

    line_id: str
    entries: List[ExplainEntry] = field(default_factory=list)

    def add(self, entry: ExplainEntry) -> None:
        self.entries.append(entry)


@dataclass
class QuoteExplain:
    """
    Container voor alle line explains + quote-level info (later uitbreidbaar).
    """

    lines: Dict[str, LineExplain] = field(default_factory=dict)

    def get_line(self, line_id: str) -> LineExplain:
        if line_id not in self.lines:
            self.lines[line_id] = LineExplain(line_id=line_id)
        return self.lines[line_id]


class ExplainCollector:
    """
    Mutatiepunt voor rules: ctx.explain.add_line_step(...)
    Houdt seq counters deterministisch bij per (line_id, order).
    """

    def __init__(self) -> None:
        self._quote = QuoteExplain()
        self._seq: Dict[tuple[str, int], int] = {}

    @property
    def quote(self) -> QuoteExplain:
        return self._quote

    def add_line_step(
        self,
        *,
        line_id: str,
        order: int,
        kind: str,
        label: str,
        delta: Decimal,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        key = (line_id, order)
        seq = self._seq.get(key, 0) + 1
        self._seq[key] = seq

        entry = ExplainEntry(
            order=order,
            seq=seq,
            kind=kind,
            label=label,
            delta=delta,
            meta=meta or {},
        )
        self._quote.get_line(line_id).add(entry)
