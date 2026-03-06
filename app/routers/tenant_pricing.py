from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Tenant
from app.schemas.tenant_pricing import (
    TenantPricingResponse,
    TenantPricingUpdate,
)

router = APIRouter(prefix="/tenant/settings/pricing", tags=["tenant-pricing"])


def get_current_tenant_id() -> str:
    return "dev-tenant"


@router.get("", response_model=TenantPricingResponse)
def get_tenant_pricing_settings(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    pricing = tenant.pricing_json or {}
    value = pricing.get("walls_rate_eur_per_sqm")

    try:
        walls_rate = float(value) if value is not None else None
    except (TypeError, ValueError):
        walls_rate = None

    return TenantPricingResponse(
        tenant_id=tenant.id,
        walls_rate_eur_per_sqm=walls_rate,
        pricing_json=pricing,
    )


@router.post("", response_model=TenantPricingResponse)
def update_tenant_pricing_settings(
    payload: TenantPricingUpdate,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    existing = tenant.pricing_json or {}
    tenant.pricing_json = {
        **existing,
        "walls_rate_eur_per_sqm": float(payload.walls_rate_eur_per_sqm),
    }

    print(
        "TENANT_PRICING_API_SAVE DEBUG BEFORE COMMIT:", tenant.id, tenant.pricing_json
    )

    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    print(
        "TENANT_PRICING_API_SAVE DEBUG AFTER REFRESH:", tenant.id, tenant.pricing_json
    )

    pricing = tenant.pricing_json or {}
    value = pricing.get("walls_rate_eur_per_sqm")
    try:
        walls_rate = float(value) if value is not None else None
    except (TypeError, ValueError):
        walls_rate = None

    return TenantPricingResponse(
        tenant_id=tenant.id,
        walls_rate_eur_per_sqm=walls_rate,
        pricing_json=pricing,
    )
