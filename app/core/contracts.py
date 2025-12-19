from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Protocol

@dataclass
class IntakeResult:
    lead_id: str
    tenant_id: str
    vertical: str
    files: list[str]

class VerticalAdapter(Protocol):
    vertical_id: str

    def render_intake_form(self, request, lead_id: str) -> Any: ...
    async def create_lead_from_form(self, request, db) -> IntakeResult: ...
