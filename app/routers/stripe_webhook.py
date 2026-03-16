import json
import os
from typing import Any, Dict

from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.tenant import Tenant

import stripe


router = APIRouter(prefix="/stripe", tags=["stripe"])


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
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    event_type = event["type"]
    data: Dict[str, Any] = event["data"]["object"]

    if event_type in {
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    }:
        subscription_id = data.get("id")
        status = data.get("status")
        trial_end = data.get("trial_end")

        if subscription_id:
            tenant = _find_tenant_by_subscription(db, subscription_id)
            if tenant:
                tenant.subscription_status = status
                if trial_end:
                    from datetime import datetime, timezone

                    tenant.trial_ends_at = datetime.fromtimestamp(
                        int(trial_end), tz=timezone.utc
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

