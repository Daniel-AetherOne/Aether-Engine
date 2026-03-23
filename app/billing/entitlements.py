from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from datetime import datetime
import logging
from typing import Protocol

from app.billing.features import (
    Feature,
    get_plan_features,
    is_subscription_accessible,
    tenant_has_feature,
)

logger = logging.getLogger(__name__)


class Action(StrEnum):
    """
    High-level billing/entitlement actions.

    These are intentionally coarse-grained so we can evolve underlying
    plan/feature mappings without touching calling code.
    """

    SEND_QUOTE = "SEND_QUOTE"
    EXPORT_PDF = "EXPORT_PDF"
    USE_BRANDING = "USE_BRANDING"
    USE_WHITELABEL = "USE_WHITELABEL"


class TenantUsageLike(Protocol):
    """
    Minimal protocol for entitlement checks.

    A concrete tenant/usage model can expose these as real attributes or
    properties; getattr() fallback keeps this resilient to partial state.
    """

    plan_code: str | None
    subscription_status: str | None
    trial_ends_at: datetime | None
    # Optional usage fields; implemented either on tenant or a related usage object.
    quotes_sent: int | None  # type: ignore[assignment]
    quote_limit: int | None  # type: ignore[assignment]


@dataclass(slots=True)
class EntitlementResult:
    """
    Normalized result for entitlement checks.

    `allowed` is the single source of truth for access decisions.
    All other fields are there purely for UX / logging / analytics.
    """

    allowed: bool
    action: str
    reason: str | None = None
    feature: str | None = None
    upgrade_url: str | None = None
    billing_url: str = "/app/billing"
    usage_limit: int | None = None
    usage_current: int | None = None
    plan_code: str | None = None
    subscription_status: str | None = None


def require_action_feature(action: str) -> str | None:
    """
    Map high-level actions to the underlying feature they depend on.
    Returns the Feature enum value string or None when no feature is required.
    """

    try:
        act = Action(action)
    except ValueError:
        return None

    if act is Action.SEND_QUOTE:
        return Feature.BASIC_SENDING.value
    if act is Action.EXPORT_PDF:
        return Feature.PDF_EXPORT.value
    if act is Action.USE_BRANDING:
        return Feature.BRANDING.value
    if act is Action.USE_WHITELABEL:
        return Feature.WHITELABEL.value
    return None


def build_upgrade_url(feature: str | None = None, action: str | None = None) -> str:
    """
    Construct a best-effort upgrade URL for UI links.
    Prefers an explicit feature, falls back to inferred feature from action.
    """

    from urllib.parse import quote

    feat = feature
    if not feat and action:
        feat = require_action_feature(action)

    if feat:
        return f"/app/billing?upgrade=1&feature={quote(feat, safe='')}"
    if action:
        return f"/app/billing?upgrade=1&action={action}"
    return "/app/billing"


def _extract_usage(tenant: TenantUsageLike | None) -> tuple[int | None, int | None]:
    """
    Extract (quotes_sent, quote_limit) from a tenant/usage-like object.
    Safe when attributes are missing or None.
    """

    if tenant is None:
        return None, None

    raw_sent = getattr(tenant, "quotes_sent", None)
    raw_limit = getattr(tenant, "quote_limit", None)

    try:
        sent = int(raw_sent) if raw_sent is not None else None
    except (TypeError, ValueError):
        sent = None

    try:
        limit = int(raw_limit) if raw_limit is not None else None
    except (TypeError, ValueError):
        limit = None

    return sent, limit


def check_entitlement(tenant: TenantUsageLike | None, action: str) -> EntitlementResult:
    """
    Central entitlement check that combines:
    - subscription status
    - feature gating
    - usage/paywall limits (where applicable)
    """

    # Defensive defaults when tenant is missing
    plan_code = getattr(tenant, "plan_code", None) if tenant is not None else None
    subscription_status = (
        getattr(tenant, "subscription_status", None) if tenant is not None else None
    )
    trial_ends_at = getattr(tenant, "trial_ends_at", None) if tenant is not None else None

    # Resolve action + feature
    try:
        act = Action(action)
    except ValueError:
        return EntitlementResult(
            allowed=False,
            action=action,
            reason="unknown_action",
            feature=None,
            upgrade_url=build_upgrade_url(action=action),
            plan_code=plan_code,
            subscription_status=subscription_status,
        )

    feature = require_action_feature(act.value)
    plan_features = sorted(get_plan_features(plan_code))

    # SEND_QUOTE: feature + subscription + usage
    if act is Action.SEND_QUOTE:
        # 1) Subscription must be accessible
        if not is_subscription_accessible(subscription_status, trial_ends_at):
            return EntitlementResult(
                allowed=False,
                action=act.value,
                reason="subscription_inactive",
                feature=feature,
                upgrade_url=build_upgrade_url(feature=feature, action=act.value),
                plan_code=plan_code,
                subscription_status=subscription_status,
            )

        # 2) Feature must be available on the plan
        if tenant is None or not tenant_has_feature(tenant, Feature.BASIC_SENDING.value):
            return EntitlementResult(
                allowed=False,
                action=act.value,
                reason="feature_not_in_plan",
                feature=feature,
                upgrade_url=build_upgrade_url(feature=feature, action=act.value),
                plan_code=plan_code,
                subscription_status=subscription_status,
            )

        # 3) Usage/paywall check (quotes_sent vs quote_limit)
        usage_current, usage_limit = _extract_usage(tenant)
        if (
            usage_limit is not None
            and usage_current is not None
            and usage_current >= usage_limit
        ):
            return EntitlementResult(
                allowed=False,
                action=act.value,
                reason="usage_limit_reached",
                feature=feature,
                upgrade_url=build_upgrade_url(feature=feature, action=act.value),
                usage_limit=usage_limit,
                usage_current=usage_current,
                plan_code=plan_code,
                subscription_status=subscription_status,
            )

        # All checks passed
        return EntitlementResult(
            allowed=True,
            action=act.value,
            reason=None,
            feature=feature,
            upgrade_url=None,
            usage_limit=usage_limit,
            usage_current=usage_current,
            plan_code=plan_code,
            subscription_status=subscription_status,
        )

    # EXPORT_PDF: subscription only; not tier-gated (matches export-pdf route policy).
    if act is Action.EXPORT_PDF:
        if not is_subscription_accessible(subscription_status, trial_ends_at):
            logger.info(
                "PDF_ENTITLEMENT_CHECK tenant_id=%s plan_code=%s subscription_status=%s action=%s allowed=%s reason=%s feature=%s features=%s",
                getattr(tenant, "id", None) if tenant is not None else None,
                plan_code,
                subscription_status,
                act.value,
                False,
                "subscription_inactive",
                feature,
                plan_features,
            )
            return EntitlementResult(
                allowed=False,
                action=act.value,
                reason="subscription_inactive",
                feature=feature,
                upgrade_url=build_upgrade_url(feature=feature, action=act.value),
                plan_code=plan_code,
                subscription_status=subscription_status,
            )
        if tenant is None:
            return EntitlementResult(
                allowed=False,
                action=act.value,
                reason="feature_not_in_plan",
                feature=feature,
                upgrade_url=build_upgrade_url(feature=feature, action=act.value),
                plan_code=plan_code,
                subscription_status=subscription_status,
            )
        logger.info(
            "PDF_ENTITLEMENT_CHECK tenant_id=%s plan_code=%s subscription_status=%s action=%s allowed=%s reason=%s feature=%s features=%s",
            getattr(tenant, "id", None),
            plan_code,
            subscription_status,
            act.value,
            True,
            None,
            feature,
            plan_features,
        )
        return EntitlementResult(
            allowed=True,
            action=act.value,
            reason=None,
            feature=feature,
            upgrade_url=None,
            plan_code=plan_code,
            subscription_status=subscription_status,
        )

    # Other actions: feature gating + subscription status (where applicable)
    if act in {Action.USE_BRANDING, Action.USE_WHITELABEL}:
        # We intentionally reuse subscription accessibility here so that
        # premium features cannot be used on inactive accounts.
        if not is_subscription_accessible(subscription_status, trial_ends_at):
            return EntitlementResult(
                allowed=False,
                action=act.value,
                reason="subscription_inactive",
                feature=feature,
                upgrade_url=build_upgrade_url(feature=feature, action=act.value),
                plan_code=plan_code,
                subscription_status=subscription_status,
            )

        if tenant is None or not tenant_has_feature(tenant, feature or ""):
            return EntitlementResult(
                allowed=False,
                action=act.value,
                reason="feature_not_in_plan",
                feature=feature,
                upgrade_url=build_upgrade_url(feature=feature, action=act.value),
                plan_code=plan_code,
                subscription_status=subscription_status,
            )

        return EntitlementResult(
            allowed=True,
            action=act.value,
            reason=None,
            feature=feature,
            upgrade_url=None,
            plan_code=plan_code,
            subscription_status=subscription_status,
        )

    # Fallback (should not be hit because all Actions are handled above).
    return EntitlementResult(
        allowed=False,
        action=act.value,
        reason="unknown_action",
        feature=feature,
        upgrade_url=build_upgrade_url(feature=feature, action=act.value),
        plan_code=plan_code,
        subscription_status=subscription_status,
    )

