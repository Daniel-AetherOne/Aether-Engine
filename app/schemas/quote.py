# app/schemas/quote.py
from typing import List, Optional
from pydantic import BaseModel


class QuoteItem(BaseModel):
    description: str
    quantity_m2: float
    unit_price: float
    total_price: float


class Quote(BaseModel):
    lead_id: int
    subtotal: float
    vat: float
    total: float
    currency: str = "EUR"
    items: List[QuoteItem]
    notes: Optional[str] = None
