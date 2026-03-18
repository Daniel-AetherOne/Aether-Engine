from __future__ import annotations

from enum import StrEnum
from typing import Iterable, Mapping, Protocol


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


PLAN_FEATURES: Mapping[str, frozenset[FeatureName]] = {
    "starter_99": frozenset(
        {
            Feature.BASIC_SENDING.value,
        }
    ),
    "pro_199": frozenset(
        {
            Feature.BASIC_SENDING.value,
            Feature.PDF_EXPORT.value,
            Feature.BRANDING.value,
        }
    ),
    "business_399": frozenset(
        {
            Feature.BASIC_SENDING.value,
            Feature.PDF_EXPORT.value,
            Feature.BRANDING.value,
            Feature.WHITELABEL.value,
        }
    ),
}


_ACCESSIBLE_STATUSES: frozenset[str] = frozenset({"active", "trialing"})


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

    code = (plan_code or "").strip()
    if not code:
        return set()
    features = PLAN_FEATURES.get(code)
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

    if not is_subscription_accessible(getattr(tenant, "subscription_status", None)):
        return False
    return plan_supports_feature(getattr(tenant, "plan_code", None), feature)


def tenant_missing_features(tenant: TenantLike, features: Iterable[str]) -> list[str]:
    """
    Return a list of features the tenant is missing, preserving input order.
    """

    return [f for f in features if not tenant_has_feature(tenant, f)]

