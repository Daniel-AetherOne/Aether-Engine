# app/verticals/ace/schemas/quote_input_v1.py
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, PositiveFloat, constr, ConfigDict


class QuoteItemV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: constr(strip_whitespace=True, min_length=1)  # type: ignore
    qty: PositiveFloat


class QuoteContextV1(BaseModel):
    """
    Context = allowlist. Alles wat je hier niet definieert, mag de UI niet sturen.
    Houd dit expres klein.
    """

    model_config = ConfigDict(extra="forbid")

    # Voorbeeld allowlist — pas aan aan jouw realiteit
    customer_segment: Optional[str] = None
    region: Optional[str] = None
    requested_date: Optional[str] = None
    notes: Optional[str] = None
    customer_id: str | None = None


class QuoteCalculateInputV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel: Literal["sales_ui"] = "sales_ui"
    items: List[QuoteItemV1] = Field(min_length=1)
    context: Optional[QuoteContextV1] = None
    idempotency_key: Optional[str] = None
