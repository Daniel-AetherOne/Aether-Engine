import os
from typing import Dict

import stripe

from app.core.settings import settings


STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")

# Environment-based mapping from internal plan_code -> Stripe price_id
PLAN_PRICE_MAPPING: Dict[str, str | None] = {
    "starter_99": os.getenv("STRIPE_PRICE_STARTER_99"),
    "pro_199": os.getenv("STRIPE_PRICE_PRO_199"),
    "business_399": os.getenv("STRIPE_PRICE_BUSINESS_399"),
}

# Base URL used for Stripe redirect URLs.
# Prefer explicit APP_BASE_URL, fall back to existing public base setting.
APP_BASE_URL: str = (os.getenv("APP_BASE_URL") or settings.APP_PUBLIC_BASE_URL).rstrip(
    "/"
)


def ensure_stripe_api_key() -> None:
    """
    Configure the global Stripe API key or raise a clear error.
    """
    key = STRIPE_SECRET_KEY
    if not key:
        raise RuntimeError("STRIPE_SECRET_KEY is not configured")

    stripe.api_key = key

