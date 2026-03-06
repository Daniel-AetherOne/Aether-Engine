from pydantic import BaseModel, Field


class TenantPricingResponse(BaseModel):
    tenant_id: str
    walls_rate_eur_per_sqm: float | None = None
    pricing_json: dict = {}


class TenantPricingUpdate(BaseModel):
    walls_rate_eur_per_sqm: float = Field(..., ge=5, le=100)