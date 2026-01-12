from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, Optional

from app.verticals.ace.explain.breakdown_builder import Breakdown

D = Decimal


@dataclass(frozen=True)
class ArticleSnapshot:
    sku: str
    buy_price: D
    weight_kg: D = D("0.0")
    supplier: Optional[str] = None
    product_group: Optional[str] = None


@dataclass
class LineState:
    # Input
    line_id: str
    sku: str
    qty: D
    meta: Dict[str, Any] = field(default_factory=dict)

    # Explainability (always present) — THIS is the only breakdown field
    breakdown: Breakdown = field(default_factory=Breakdown)

    # Snapshot from dataset
    article: Optional[ArticleSnapshot] = None

    # Computed (MVP)
    net_cost: D = D("0.00")
    tier_discount_pct: D = D("0.00")
    customer_discount_pct: D = D("0.00")
    transport_cost: D = D("0.00")
    net_sell: D = D("0.00")
    margin_pct: D = D("0.00")

    def add_breakdown(self, msg: str) -> None:
        """
        Backward compatible helper: old tests call add_breakdown(str).
        We keep it, but route into Breakdown so everything stays consistent.
        """
        self.breakdown.add_step("META", str(msg))

    @staticmethod
    def q(x: D) -> D:
        return x.quantize(D("0.01"))


def load_article_snapshot(
    tables: Dict[str, Any], sku: str
) -> Optional[ArticleSnapshot]:
    """
    MVP expectation:
      tables["articles"][sku] = {
        "buyPrice": "10.00",
        "weightKg": "2.5",
        "supplier": "X",
        "productGroup": "A"
      }
    """
    articles = (tables or {}).get("articles") or {}
    row = articles.get(sku)
    if not row:
        return None

    return ArticleSnapshot(
        sku=sku,
        buy_price=D(str(row.get("buyPrice", "0"))),
        weight_kg=D(str(row.get("weightKg", "0"))),
        supplier=row.get("supplier"),
        product_group=row.get("productGroup"),
    )
