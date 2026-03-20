from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.billing.features import PLAN_FEATURES
from app.db import get_db
from app.models.tenant import Tenant
from app.models.user import User
from app.services.stripe_service import StripeService, compute_trial_end


AllowedStatus = Literal["trialing", "active", "past_due", "canceled"]


router = APIRouter(prefix="/billing", tags=["billing"])


def _get_tenant_for_user(user: User, db: Session) -> Tenant:
    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=400, detail="Tenant not found")
    return tenant


@router.post("/start-trial")
def start_trial(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stripe_service = StripeService()

    tenant = _get_tenant_for_user(user, db)

    # 1) Ensure customer
    if not tenant.stripe_customer_id:
        customer = stripe_service.create_customer(email=tenant.email or user.email)
        tenant.stripe_customer_id = customer.id

    # 2) Create subscription with 14 day trial
    subscription = stripe_service.create_trial_subscription(
        customer_id=tenant.stripe_customer_id,
        trial_days=14,
    )

    tenant.stripe_subscription_id = subscription.id
    status: str = getattr(subscription, "status", "trialing")
    tenant.subscription_status = status
    # Keep internal plan codes stable for entitlement checks.
    # Stripe subscription payload can return price/plan IDs that do not match
    # our internal mapping keys.
    subscription_plan_code = getattr(subscription, "plan", {}).get("id") if getattr(
        subscription, "plan", None
    ) else None
    tenant.plan_code = (
        subscription_plan_code
        if subscription_plan_code in PLAN_FEATURES
        else (tenant.plan_code or "starter_99")
    )

    trial_end = getattr(subscription, "trial_end", None)
    tenant.trial_ends_at = compute_trial_end(trial_end)

    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    return RedirectResponse(url="/app", status_code=303)


def require_active_subscription(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Tenant:
    tenant = _get_tenant_for_user(user, db)

    status = tenant.subscription_status or "trialing"
    now = datetime.now(timezone.utc)

    if status == "active":
        return tenant

    if status == "trialing" and tenant.trial_ends_at and tenant.trial_ends_at > now:
        return tenant

    raise HTTPException(
        status_code=303,
        detail="Subscription inactive",
        headers={"Location": "/app/billing"},
    )

