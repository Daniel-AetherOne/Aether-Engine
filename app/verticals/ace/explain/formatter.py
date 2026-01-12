# app/verticals/ace/explain/formatter.py
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import List

from .explain_models import ExplainEntry


def money(eur: Decimal) -> str:
    # MVP: simpele format, later locale-aware
    q = eur.quantize(Decimal("0.01"))
    s = f"{q:.2f}"
    return f"€ {s}"


@dataclass(frozen=True)
class FormatOptions:
    show_plus_sign: bool = True


class ExplainFormatter:
    def __init__(self, opts: FormatOptions | None = None) -> None:
        self._opts = opts or FormatOptions()

    def format_line_entries(self, entries: List[ExplainEntry]) -> List[str]:
        """
        Output = list[str] regels, klaar voor UI/Excel/mail.
        """
        lines: List[str] = []
        for e in entries:
            lines.append(self._format_entry(e))
        return lines

    def _format_entry(self, e: ExplainEntry) -> str:
        d = e.delta
        if d == Decimal("0"):
            return f"{e.label}"
        sign = ""
        if self._opts.show_plus_sign and d > 0:
            sign = "+"
        return f"{e.label}: {sign}{money(d)}"
