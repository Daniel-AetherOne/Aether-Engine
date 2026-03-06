# app/schemas/onboarding.py
from pydantic import BaseModel, EmailStr, Field


class TenantOnboardingCreate(BaseModel):
    company_name: str = Field(..., min_length=2, max_length=200)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=50)
    walls_rate_eur_per_sqm: float = Field(..., gt=0)


class TenantOnboardingResponse(BaseModel):
    tenant_id: str
    company_name: str
    email: str
    phone: str | None = None
    pricing_json: dict
