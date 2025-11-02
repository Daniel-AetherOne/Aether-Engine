# app/schemas/intake.py
from pydantic import BaseModel, EmailStr
from typing import List, Optional

class IntakePayload(BaseModel):
    # Optioneel: UI stuurt dit (nog) niet mee; backend default naar "default"
    tenant_id: Optional[str] = None

    # Lead data uit het formulier
    name: str
    email: EmailStr
    phone: Optional[str] = None
    project_description: Optional[str] = None

    # Tijdelijke upload keys (zonder tenant-prefix), bijv. "uploads/2025-11-01/<uuid>/TEST.jpg"
    object_keys: List[str] = []
