from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import uuid4

D = Decimal


@dataclass(frozen=True)
class Money:
    currency: str
    amount: D

    def quantized(self) -> "Money":
        return Money(self.currency, self.amount.quantize(D("0.01")))


@dataclass(frozen=True)
class PriceBreakdownLineV1:
    rule_id: str
    rule_type: str
    title: str
    decision: str  # "APPLIED" | "SKIPPED" | "BLOCKED"
    delta: Money
    subtotal_after: Money
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class QuoteOutputV1:
    version: str  # "v1"
    currency: str
    status: str  # "OK" | "BLOCKED"
    total: Money
    price_breakdown: List[PriceBreakdownLineV1]
    blocks: List[Dict[str, Any]] = field(default_factory=list)


# -----------------------------
# Input models (MVP + backward compatible)
# -----------------------------


@dataclass
class QuoteLineInput:
    """
    MVP line. Later kun je dit koppelen aan articles/tiers/etc.
    """

    line_id: str
    base_amount: D = D("0.00")
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class QuoteInput:
    """
    Backward compatible met jouw huidige usage,
    plus 3.2 velden toegevoegd.
    """

    currency: str = "EUR"
    base_amount: D = D("0.00")

    # Simpele cost inputs
    material_cost: D = D("0.00")
    labor_cost: D = D("0.00")
    transport_km: D = D("0.00")

    # Klant / deal
    customer_segment: Optional[str] = None
    discount_percent: Optional[D] = None

    # 3.2: context velden
    customer_id: Optional[str] = None
    ship_to_postcode: Optional[str] = None
    country: Optional[str] = None

    # 3.2: lines (optioneel, MVP: leeg => single synthetic line)
    lines: List[QuoteLineInput] = field(default_factory=list)

    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ActiveData:
    """
    Placeholder voor je Phase-2 bundle (tariffs, tables, etc.).
    """

    tables: Dict[str, Any] = field(default_factory=dict)


# -----------------------------
# Runtime state (per request)
# -----------------------------


@dataclass
class QuoteState:
    currency: str
    subtotal: D
    breakdown: List[PriceBreakdownLineV1] = field(default_factory=list)
    blocks: List[Dict[str, Any]] = field(default_factory=list)

    def money(self, amount: D) -> Money:
        return Money(self.currency, amount).quantized()


@dataclass
class LineState:
    """
    Per line mutable state. MVP: we houden alleen subtotal bij.
    """

    line_id: str
    subtotal: D
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EngineContext:
    """
    3.2 — Execution context (per request, stateless outside this object).

    Bevat:
    - input (QuoteInput)
    - active data (ActiveData)
    - runtime: quote_id, now, contract_version
    - output accumulators: warnings, blocking
    - quote state: subtotal/breakdown/blocks
    """

    input: QuoteInput
    data: ActiveData
    contract_version: str = "v1"
    quote_id: str = field(default_factory=lambda: uuid4().hex)
    now: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    warnings: List[Dict[str, Any]] = field(default_factory=list)
    blocking: List[Dict[str, Any]] = field(default_factory=list)

    state: QuoteState = field(init=False)

    def __post_init__(self) -> None:
        self.state = QuoteState(
            currency=self.input.currency, subtotal=self.input.base_amount
        )
        # laat blocks shared zijn (1 bron)
        self.state.blocks = self.blocking

    def warn(self, code: str, message: str, **meta: Any) -> None:
        self.warnings.append({"code": code, "message": message, "meta": meta})

    def block(self, code: str, message: str, **meta: Any) -> None:
        self.blocking.append({"code": code, "message": message, "meta": meta})
