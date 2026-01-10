from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional, Literal

from pydantic import BaseModel, ConfigDict, Field, condecimal


Money = condecimal(max_digits=12, decimal_places=2)


class PricingMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estimate_id: str
    date: date
    valid_until: Optional[date] = None
    currency: str = Field("USD", pattern="^[A-Z]{3}$")


class PricingSubtotals(BaseModel):
    model_config = ConfigDict(extra="forbid")

    labor: Money = Decimal("0.00")
    materials: Money = Decimal("0.00")


class PricingTotals(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pre_tax: Money
    grand_total: Money


class PricingTax(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tax_label: str = "Sales tax"
    tax_rate: Optional[Decimal] = None  # bijv Decimal("0.0825")
    tax_amount: Optional[Money] = None  # bijv Decimal("12.34")


class PricingLineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    label: str
    quantity: float = Field(..., gt=0)
    unit: str
    unit_price: Money
    total: Money
    category: Literal["labor", "materials", "other"] = "labor"
    description: Optional[str] = None
    assumptions: Optional[Dict[str, Any]] = None


class PricingOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"

    meta: PricingMeta
    line_items: List[PricingLineItem]

    subtotals: PricingSubtotals
    totals: PricingTotals

    tax: Optional[PricingTax] = None
    notes: List[str] = Field(default_factory=list)
