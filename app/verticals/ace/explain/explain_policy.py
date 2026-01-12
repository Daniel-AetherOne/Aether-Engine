# app/verticals/ace/explain/explain_policy.py
from __future__ import annotations

from decimal import Decimal
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from .explain_models import ExplainEntry


class ExplainPolicy:
    ALWAYS_KINDS = {"BASE", "NET_COST", "MIN_MARGIN"}  # uitbreidbaar

    def filter_entries(self, entries: List["ExplainEntry"]) -> List["ExplainEntry"]:
        """
        Policy A (MVP):
        - Toon alleen entries die effect hebben (delta != 0)
        - PLUS altijd BASE / NET_COST / MIN_MARGIN (ook bij delta 0)
        """
        out: List["ExplainEntry"] = []
        for e in entries:
            always = e.kind in self.ALWAYS_KINDS
            has_effect = getattr(e, "delta", Decimal("0.00")) != Decimal("0.00")
            if always or has_effect:
                out.append(e)
        return out

    def render_entry(self, e: "ExplainEntry") -> str:
        """
        MVP: render direct label (straks strict via templates).
        """
        return str(e.label)
