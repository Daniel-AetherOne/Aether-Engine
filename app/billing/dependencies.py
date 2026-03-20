from __future__ import annotations

from collections.abc import Callable
import logging
from typing import Any
from urllib.parse import quote

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.billing.features import get_plan_features, tenant_has_feature
from app.billing.entitlements import EntitlementResult, check_entitlement
from app.db import get_db
from app.models.tenant import Tenant
from app.models.user import User


logger = logging.getLogger(__name__)


def _get_tenant_for_user(user: User, db: Session) -> Tenant:
    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=400, detail="Tenant not found")
    return tenant


def _log_feature_denied(*, tenant: Tenant, feature: str, path: str | None) -> None:
    """
    Lightweight support log for denied premium feature attempts.

    Intentionally logs only:
    - tenant_id
    - plan_code
    - subscription_status
    - feature
    - path (if available)
    """

    logger.info(
        "feature_access_denied",
        extra={
            "tenant_id": getattr(tenant, "id", None),
            "plan_code": getattr(tenant, "plan_code", None),
            "subscription_status": getattr(tenant, "subscription_status", None),
            "feature": feature,
            "path": path,
        },
    )


def _raise_feature_error(*, tenant: Tenant, feature: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "error": "feature_not_available",
            "feature": feature,
            "plan_code": tenant.plan_code,
            "billing_url": "/app/billing",
        },
    )


def _raise_feature_redirect(*, feature: str) -> None:
    qs_feature = quote(feature, safe="")
    raise HTTPException(
        status_code=status.HTTP_303_SEE_OTHER,
        detail="Feature not available",
        headers={"Location": f"/app/billing?upgrade=1&feature={qs_feature}"},
    )


def require_feature(
    feature: str, *, redirect_to_billing: bool = False
) -> Callable[..., Tenant]:
    """
    Dependency factory that enforces access to a single feature.

    - Returns the current `Tenant` when access is granted.
    - Otherwise raises:
      - 403 JSON error by default
      - 303 redirect to billing when `redirect_to_billing=True`
    """

    def _dep(
        request: Request,
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> Tenant:
        tenant = _get_tenant_for_user(user=user, db=db)
        if tenant_has_feature(tenant, feature):
            return tenant
        _log_feature_denied(tenant=tenant, feature=feature, path=str(request.url.path))
        if redirect_to_billing:
            _raise_feature_redirect(feature=feature)
        _raise_feature_error(tenant=tenant, feature=feature)

    return _dep


def require_entitlement(action: str) -> Callable[..., Tenant]:
    """
    Dependency factory that enforces a high-level billing entitlement.

    Uses `check_entitlement` to combine subscription, feature, and usage/paywall.
    Returns the current `Tenant` when allowed, otherwise raises 403 with a
    structured entitlement payload.
    """

    def _dep(
        request: Request,
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> Tenant:
        tenant = _get_tenant_for_user(user=user, db=db)
        if action == "EXPORT_PDF":
            logger.info(
                "PDF_REQUEST_START tenant_id=%s plan_code=%s subscription_status=%s action=%s path=%s",
                getattr(tenant, "id", None),
                getattr(tenant, "plan_code", None),
                getattr(tenant, "subscription_status", None),
                action,
                str(request.url.path),
            )
        result: EntitlementResult = check_entitlement(tenant, action)
        plan_features = sorted(get_plan_features(getattr(tenant, "plan_code", None)))
        if result.allowed:
            if action == "EXPORT_PDF":
                logger.info(
                    "PDF_ENTITLEMENT_RESULT tenant_id=%s action=%s allowed=%s reason=%s plan_code=%s subscription_status=%s feature=%s features=%s path=%s",
                    getattr(tenant, "id", None),
                    result.action,
                    True,
                    None,
                    result.plan_code,
                    result.subscription_status,
                    result.feature,
                    plan_features,
                    str(request.url.path),
                )
            return tenant

        logger.info(
            "entitlement_denied",
            extra={
                "tenant_id": getattr(tenant, "id", None),
                "action": result.action,
                "reason": result.reason,
                "feature": result.feature,
                "plan_code": result.plan_code,
                "subscription_status": result.subscription_status,
                "usage_limit": result.usage_limit,
                "usage_current": result.usage_current,
                "path": str(request.url.path),
                "features": plan_features,
            },
        )
        if action == "EXPORT_PDF":
            logger.info(
                "PDF_ENTITLEMENT_RESULT tenant_id=%s action=%s allowed=%s reason=%s plan_code=%s subscription_status=%s feature=%s features=%s path=%s",
                getattr(tenant, "id", None),
                result.action,
                False,
                result.reason,
                result.plan_code,
                result.subscription_status,
                result.feature,
                plan_features,
                str(request.url.path),
            )

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "entitlement_denied",
                "reason": result.reason,
                "action": result.action,
                "feature": result.feature,
                "plan_code": result.plan_code,
                "subscription_status": result.subscription_status,
                "billing_url": result.billing_url,
                "upgrade_url": result.upgrade_url,
                "usage_limit": result.usage_limit,
                "usage_current": result.usage_current,
            },
        )

    return _dep


def require_any_feature(
    features: list[str], *, redirect_to_billing: bool = False
) -> Callable[..., Tenant]:
    """
    Dependency factory that enforces access to at least one of the given features.
    """

    wanted = [f for f in features if f]

    def _dep(
        request: Request,
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> Tenant:
        tenant = _get_tenant_for_user(user=user, db=db)
        allowed = any(tenant_has_feature(tenant, f) for f in wanted)
        if allowed:
            return tenant
        feature = wanted[0] if wanted else ""
        _log_feature_denied(tenant=tenant, feature=feature, path=str(request.url.path))
        if redirect_to_billing:
            _raise_feature_redirect(feature=feature)
        _raise_feature_error(tenant=tenant, feature=feature)

    return _dep


def ensure_feature_or_redirect(
    request: Request, tenant: Tenant, feature: str
) -> RedirectResponse | None:
    """
    Utility for HTML routes.

    If missing, returns a 303 RedirectResponse to billing. Otherwise returns None.
    """

    _ = request  # kept for call-site ergonomics / future context (next URL, etc.)
    if tenant_has_feature(tenant, feature):
        return None
    qs_feature = quote(feature, safe="")
    return RedirectResponse(
        url=f"/app/billing?upgrade=1&feature={qs_feature}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


def ensure_entitlement_or_redirect(
    request: Request, tenant: Tenant, action: str
) -> RedirectResponse | None:
    """
    HTML helper for entitlement-based gating.

    If the entitlement is denied, returns a 303 redirect to billing/upgrade.
    Otherwise returns None.
    """

    result = check_entitlement(tenant, action)
    if result.allowed:
        return None

    target = result.upgrade_url or result.billing_url or "/app/billing"
    return RedirectResponse(url=target, status_code=status.HTTP_303_SEE_OTHER)


