from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Article:
    sku: str
    description: str
    cost: float
    currency: str
    weight_kg: float


@dataclass(frozen=True)
class TierRow:
    from_qty: int
    to_qty: Optional[int]  # None = open-ended
    discount_pct: float


@dataclass(frozen=True)
class SupplierFactor:
    supplier: str
    factor: float
    currency_markup_pct: float


@dataclass(frozen=True)
class TransportRow:
    postcode: str
    zone: str
    eur_per_kg: float


@dataclass(frozen=True)
class Customer:
    customer_id: str
    discount_profile: str
    max_extra_discount_pct: float
