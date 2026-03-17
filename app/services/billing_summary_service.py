from typing import Any, Dict

from sqlalchemy.orm import Session

from app.config.plans import PLANS
from app.services.usage_service import get_or_create_usage


PLAN_LABELS: Dict[str, str] = {
    "starter_99": "Starter",
    "pro_199": "Pro",
    "business_399": "Business",
}


def get_billing_usage_summary(db: Session, tenant: Any) -> Dict[str, Any]:
    """
    Return a summary of billing usage for a tenant.
    """
    plan_key = tenant.plan_code or "starter_99"
    plan = PLANS.get(plan_key, PLANS["starter_99"])
    quote_limit = plan.get("quote_limit")
    plan_label = PLAN_LABELS.get(plan_key, plan_key)

    usage = get_or_create_usage(db, str(tenant.id))
    quotes_sent = usage.quotes_sent or 0

    if quote_limit is None:
        is_unlimited = True
        quotes_remaining = None
        usage_percent = 0
    else:
        is_unlimited = False
        quotes_remaining = max(quote_limit - quotes_sent, 0)

        if quote_limit > 0:
            usage_percent = min(int((quotes_sent / quote_limit) * 100), 100)
        else:
            usage_percent = 0

    return {
        "plan_code": plan_key,
        "plan_label": plan_label,
        "quotes_sent": quotes_sent,
        "quote_limit": quote_limit,
        "quotes_remaining": quotes_remaining,
        "usage_percent": usage_percent,
        "is_unlimited": is_unlimited,
    }

