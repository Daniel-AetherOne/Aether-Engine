import os
from typing import Dict

import stripe

from app.core.settings import settings
from app.core.plan_catalog import PLAN_CATALOG


STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")

# Backwards-compatible mapping export, derived from the central plan catalog.
PLAN_PRICE_MAPPING: Dict[str, str | None] = {
    code: (os.getenv(item.stripe_price_env_key) or "").strip() or None
    for code, item in PLAN_CATALOG.items()
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

