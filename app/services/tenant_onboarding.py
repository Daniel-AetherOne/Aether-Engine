# app/services/tenant_onboarding.py
import uuid
from sqlalchemy.orm import Session

from app.models.tenant import Tenant
from app.schemas.onboarding import TenantOnboardingCreate


def create_tenant_with_pricing(db: Session, payload: TenantOnboardingCreate) -> Tenant:
    company_name = payload.company_name.strip()
    email = payload.email.lower().strip()
    phone = payload.phone.strip() if payload.phone else None

    tenant = Tenant(
        id=str(uuid.uuid4()),
        name=company_name,  # tijdelijk gelijk houden aan company_name
        company_name=company_name,
        email=email,
        phone=phone,
        pricing_json={
            "walls_rate_eur_per_sqm": float(payload.walls_rate_eur_per_sqm),
        },
    )

    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant