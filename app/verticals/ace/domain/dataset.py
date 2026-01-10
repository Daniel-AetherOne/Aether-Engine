from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .models import Article, TierRow, SupplierFactor, TransportRow, Customer


@dataclass(frozen=True)
class DatasetBundle:
    active_version_id: str

    articles: dict[str, Article]               # sku -> Article
    tiers: list[TierRow]                       # ordered by from_qty
    supplier_factors: dict[str, SupplierFactor]# supplier -> Factor
    transport: list[TransportRow]              # raw table
    customers: dict[str, Customer]             # customer_id -> Customer
