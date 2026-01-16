# app/verticals/ace/schemas/quote_output_v1.py
from __future__ import annotations

from typing import Any, Dict, Literal
from pydantic import BaseModel, ConfigDict


class QuoteOutputV1(BaseModel):
    """
    Minimal output lock voor 5.1:
    - top-level velden zijn strikt
    - rest van de engine output gaat 1-op-1 mee in payload
    - geen extra top-level velden toegestaan (anti-Excel)
    """

    model_config = ConfigDict(extra="forbid")

    version: Literal["v1"] = "v1"
    calculation_id: str
    engine_version: str
    status: Literal["ok", "warning", "blocking"]

    # volledige engine output (contract v1) als blob; UI rendert read-only
    payload: Dict[str, Any]
