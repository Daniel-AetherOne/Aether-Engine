from __future__ import annotations

from enum import StrEnum
from typing import Iterable, Mapping, Protocol
import logging

from app.core.plan_catalog import (
    DEFAULT_PLAN_CODE,
    PLAN_CODE_ALIASES,
    PLAN_CATALOG,
    resolve_plan_code,
)


class Feature(StrEnum):
    """
    Central feature registry for plan gating.

    Values are stable string identifiers to keep storage/telemetry consistent.
    """

    BASIC_SENDING = "BASIC_SENDING"
    PDF_EXPORT = "PDF_EXPORT"
    BRANDING = "BRANDING"
    WHITELABEL = "WHITELABEL"


FeatureName = str
logger = logging.getLogger(__name__)


PLAN_FEATURES: Mapping[str, frozenset[FeatureName]] = {
    code: item.entitlement_features for code, item in PLAN_CATALOG.items()
}


_ACCESSIBLE_STATUSES: frozenset[str] = frozenset({"active", "trialing"})
_PLAN_CODE_ALIASES: Mapping[str, str] = PLAN_CODE_ALIASES


def is_subscription_accessible(subscription_status: str | None) -> bool:
    """
    Return whether a tenant's subscription should be treated as granting access.

    Accessible statuses are: "active" and "trialing".
    Non-accessible statuses are: "inactive", "past_due", "canceled", and None.
    Unknown statuses are treated as non-accessible.

    Defensive behavior:
    - Whitespace is ignored
    - Status comparison is case-insensitive
    """

    status = (subscription_status or "").strip().lower()
    if not status:
        return False
    return status in _ACCESSIBLE_STATUSES


def get_plan_features(plan_code: str | None) -> set[FeatureName]:
    """
    Return the feature set for a plan code.

    Safe for None or unknown plan codes: returns an empty set.

    Defensive behavior:
    - Whitespace is ignored
    """

    # Default to Starter when plan code is missing in dev/runtime records.
    normalized = resolve_plan_code(plan_code, allow_aliases=True) or DEFAULT_PLAN_CODE
    features = PLAN_FEATURES.get(normalized)
    return set(features) if features else set()


def plan_supports_feature(plan_code: str | None, feature: str) -> bool:
    """
    Return whether a plan includes the given feature.

    Unknown plan codes or features return False.
    """

    if not feature:
        return False
    return feature in get_plan_features(plan_code)


class TenantLike(Protocol):
    plan_code: str | None
    subscription_status: str | None


def tenant_has_feature(tenant: TenantLike, feature: str) -> bool:
    """
    Return whether the tenant currently has access to the given feature.

    Rules:
    - First require an accessible subscription status (active or trialing)
    - Then check whether the tenant plan includes the feature
    """

    subscription_status = getattr(tenant, "subscription_status", None)
    plan_code = getattr(tenant, "plan_code", None)
    resolved_features = sorted(get_plan_features(plan_code))
    if not is_subscription_accessible(subscription_status):
        if feature == Feature.PDF_EXPORT.value:
            logger.info(
                "PDF_TENANT_HAS_FEATURE plan_code=%s subscription_status=%s feature=%s resolved_features=%s result=%s",
                plan_code,
                subscription_status,
                feature,
                resolved_features,
                False,
            )
        return False
    result = plan_supports_feature(plan_code, feature)
    if feature == Feature.PDF_EXPORT.value:
        logger.info(
            "PDF_TENANT_HAS_FEATURE plan_code=%s subscription_status=%s feature=%s resolved_features=%s result=%s",
            plan_code,
            subscription_status,
            feature,
            resolved_features,
            result,
        )
    return result


def tenant_missing_features(tenant: TenantLike, features: Iterable[str]) -> list[str]:
    """
    Return a list of features the tenant is missing, preserving input order.
    """

    return [f for f in features if not tenant_has_feature(tenant, f)]

