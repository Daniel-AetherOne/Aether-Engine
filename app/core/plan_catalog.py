from __future__ import annotations

import os
from dataclasses import dataclass


DEFAULT_PLAN_CODE = "starter_99"
CANONICAL_PLAN_CODES: tuple[str, ...] = (
    "starter_99",
    "pro_199",
    "business_399",
)

# Temporary backwards-compatible aliases for historic/external inputs.
PLAN_CODE_ALIASES: dict[str, str] = {
    "starter": "starter_99",
    "starter_monthly": "starter_99",
    "starter-yearly": "starter_99",
    "pro": "pro_199",
    "business": "business_399",
}


@dataclass(frozen=True, slots=True)
class PlanCatalogItem:
    code: str
    name: str
    price_label: str
    quote_limit_label: str
    ui_features: tuple[str, ...]
    entitlement_features: frozenset[str]
    stripe_price_env_key: str


PLAN_CATALOG: dict[str, PlanCatalogItem] = {
    "starter_99": PlanCatalogItem(
        code="starter_99",
        name="Starter",
        price_label="EUR99 / month",
        quote_limit_label="99 quotes / month",
        ui_features=("Basic sending", "PDF export"),
        entitlement_features=frozenset(
            {
                "BASIC_SENDING",
                "PDF_EXPORT",
            }
        ),
        stripe_price_env_key="STRIPE_PRICE_STARTER_99",
    ),
    "pro_199": PlanCatalogItem(
        code="pro_199",
        name="Pro",
        price_label="EUR199 / month",
        quote_limit_label="200 quotes / month",
        ui_features=("Basic sending", "PDF export", "Branding/logo"),
        entitlement_features=frozenset(
            {
                "BASIC_SENDING",
                "PDF_EXPORT",
                "BRANDING",
            }
        ),
        stripe_price_env_key="STRIPE_PRICE_PRO_199",
    ),
    "business_399": PlanCatalogItem(
        code="business_399",
        name="Business",
        price_label="EUR399 / month",
        quote_limit_label="Unlimited quotes / month",
        ui_features=("Basic sending", "PDF export", "Branding/logo", "Whitelabel"),
        entitlement_features=frozenset(
            {
                "BASIC_SENDING",
                "PDF_EXPORT",
                "BRANDING",
                "WHITELABEL",
            }
        ),
        stripe_price_env_key="STRIPE_PRICE_BUSINESS_399",
    ),
}


def resolve_plan_code(plan_code: str | None, *, allow_aliases: bool = True) -> str | None:
    code = (plan_code or "").strip()
    if not code:
        return DEFAULT_PLAN_CODE
    if code in PLAN_CATALOG:
        return code
    if allow_aliases:
        return PLAN_CODE_ALIASES.get(code.lower())
    return None


def get_plan_item(plan_code: str | None, *, allow_aliases: bool = True) -> PlanCatalogItem | None:
    resolved = resolve_plan_code(plan_code, allow_aliases=allow_aliases)
    if not resolved:
        return None
    return PLAN_CATALOG.get(resolved)


def get_stripe_price_id(plan_code: str | None) -> tuple[str | None, str | None]:
    item = get_plan_item(plan_code, allow_aliases=True)
    if not item:
        return None, None
    return item.code, (os.getenv(item.stripe_price_env_key) or "").strip() or None

