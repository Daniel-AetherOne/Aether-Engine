# app/services/tenant_onboarding.py
import re
import uuid
from sqlalchemy.orm import Session

from app.models.tenant import Tenant
from app.schemas.onboarding import TenantOnboardingCreate


def _slugify_company_name(company_name: str) -> str:
    """
    Minimal, URL-safe slugifier:
    - lowercase
    - replace non-alphanumeric with hyphens
    - collapse multiple hyphens
    - strip leading/trailing hyphens
    """
    base = company_name.strip().lower()
    base = re.sub(r"[^a-z0-9]+", "-", base)
    base = re.sub(r"-{2,}", "-", base).strip("-")
    return base or "tenant"


def _ensure_unique_slug(db: Session, base_slug: str) -> str:
    """
    Ensure slug uniqueness by appending a short numeric suffix if needed.
    """
    slug = base_slug
    counter = 2

    while db.query(Tenant).filter(Tenant.slug == slug).first() is not None:
        slug = f"{base_slug}-{counter}"
        counter += 1

    return slug


def create_tenant_with_pricing(db: Session, payload: TenantOnboardingCreate) -> Tenant:
    company_name = payload.company_name.strip()
    email = payload.email.lower().strip()
    phone = payload.phone.strip() if payload.phone else None

    base_slug = _slugify_company_name(company_name)
    unique_slug = _ensure_unique_slug(db, base_slug)

    tenant = Tenant(
        id=str(uuid.uuid4()),
        name=company_name,  # tijdelijk gelijk houden aan company_name
        company_name=company_name,
        email=email,
        phone=phone,
        slug=unique_slug,
        plan_code="starter_99",
        subscription_status="trialing",
        pricing_json={
            "walls_rate_eur_per_sqm": float(payload.walls_rate_eur_per_sqm),
        },
    )

    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant