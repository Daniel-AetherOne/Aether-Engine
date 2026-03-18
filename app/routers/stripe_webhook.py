import json
import os
from typing import Any, Dict

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.tenant import Tenant

import stripe
import logging


router = APIRouter(prefix="/stripe", tags=["stripe"])
logger = logging.getLogger(__name__)


STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY


def _find_tenant_by_subscription(db: Session, subscription_id: str) -> Tenant | None:
    return (
        db.query(Tenant)
        .filter(Tenant.stripe_subscription_id == subscription_id)
        .first()
    )


def _find_tenant_by_id(db: Session, tenant_id: str | None) -> Tenant | None:
    if not tenant_id:
        return None
    return db.query(Tenant).filter(Tenant.id == tenant_id).first()


@router.post("/webhook", include_in_schema=False, response_model=None)
async def stripe_webhook(
    request: Request,
    db: Session = Depends(get_db),
    stripe_signature: str | None = Header(None, alias="Stripe-Signature"),
):
    payload = await request.body()

    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=500, detail="Webhook secret not configured")

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=stripe_signature,
            secret=STRIPE_WEBHOOK_SECRET,
        )
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid webhook payload")

    event_type = event["type"]
    data: Dict[str, Any] = event["data"]["object"]

    if event_type == "checkout.session.completed":
        # Primary coupling via tenant_id from metadata.
        metadata = data.get("metadata") or {}
        tenant_id = metadata.get("tenant_id")
        target_plan_code = metadata.get("target_plan_code")

        tenant = _find_tenant_by_id(db, tenant_id)
        if tenant:
            customer_id = data.get("customer")
            subscription_id = data.get("subscription")

            if customer_id:
                tenant.stripe_customer_id = customer_id
            if subscription_id:
                tenant.stripe_subscription_id = subscription_id
            if target_plan_code:
                tenant.plan_code = target_plan_code

            db.add(tenant)
            db.commit()

    elif event_type in {
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    }:
        metadata = data.get("metadata") or {}
        tenant_id = metadata.get("tenant_id")
        plan_code = metadata.get("plan_code")

        subscription_id = data.get("id")
        status = data.get("status")
        customer_id = data.get("customer")
        trial_end = data.get("trial_end")
        current_period_end = data.get("current_period_end")

        tenant = _find_tenant_by_id(db, tenant_id)
        if not tenant and subscription_id:
            tenant = _find_tenant_by_subscription(db, subscription_id)

        if tenant:
            if customer_id:
                tenant.stripe_customer_id = customer_id
            if subscription_id:
                tenant.stripe_subscription_id = subscription_id

            if event_type == "customer.subscription.deleted":
                tenant.subscription_status = "canceled"
                tenant.plan_code = "starter_99"
            else:
                if status:
                    tenant.subscription_status = status
                if plan_code:
                    tenant.plan_code = plan_code

                if trial_end:
                    from datetime import datetime, timezone

                    tenant.trial_ends_at = datetime.fromtimestamp(
                        int(trial_end), tz=timezone.utc
                    )

                if current_period_end and hasattr(
                    tenant, "subscription_current_period_end"
                ):
                    from datetime import datetime, timezone

                    tenant.subscription_current_period_end = datetime.fromtimestamp(
                        int(current_period_end), tz=timezone.utc
                    )

            db.add(tenant)
            db.commit()

    elif event_type == "invoice.payment_failed":
        subscription_id = data.get("subscription")
        if subscription_id:
            tenant = _find_tenant_by_subscription(db, subscription_id)
            if tenant:
                tenant.subscription_status = "past_due"
                db.add(tenant)
                db.commit()

    return {"received": True}
