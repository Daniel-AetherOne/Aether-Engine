# app/routers/onboarding.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.tenant import Tenant
from app.schemas.onboarding import (
    TenantOnboardingCreate,
    TenantOnboardingResponse,
)
from app.services.tenant_onboarding import create_tenant_with_pricing

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.post("/tenant", response_model=TenantOnboardingResponse)
def onboard_tenant(
    payload: TenantOnboardingCreate,
    db: Session = Depends(get_db),
):
    email = payload.email.lower().strip()

    existing = db.query(Tenant).filter(Tenant.email == email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already exists")

    tenant = create_tenant_with_pricing(db=db, payload=payload)

    return TenantOnboardingResponse(
        tenant_id=tenant.id,
        company_name=tenant.company_name or tenant.name,
        email=tenant.email or "",
        phone=tenant.phone,
        pricing_json=tenant.pricing_json or {},
    )