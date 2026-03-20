from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol
from urllib.parse import quote

from app.billing.features import Feature, tenant_has_feature
from app.billing.entitlements import Action, EntitlementResult, check_entitlement


class TenantLike(Protocol):
    plan_code: str | None
    subscription_status: str | None


@dataclass(frozen=True, slots=True)
class FeatureUI:
    """
    Small viewmodel for templates/UI.

    `enabled` uses the same gating rules as the backend: subscription accessible + plan includes feature.
    """

    enabled: bool
    upgrade_url: str
    hint: str | None = None


_DEFAULT_HINTS: Mapping[str, str] = {
    Feature.BASIC_SENDING.value: "Beschikbaar vanaf Starter",
    Feature.PDF_EXPORT.value: "Beschikbaar vanaf Starter",
    Feature.BRANDING.value: "Beschikbaar vanaf Pro",
    Feature.WHITELABEL.value: "Beschikbaar vanaf Business",
}


def _upgrade_url(feature: str) -> str:
    return f"/app/billing?upgrade=1&feature={quote(feature, safe='')}"


def tenant_feature_flags(tenant: TenantLike | None) -> dict[str, bool]:
    """
    Minimal boolean flags for templates/dashboards.
    """

    if tenant is None:
        return {
            "basic_sending": False,
            "pdf_export": False,
            "branding": False,
            "whitelabel": False,
        }

    return {
        "basic_sending": tenant_has_feature(tenant, Feature.BASIC_SENDING.value),
        "pdf_export": tenant_has_feature(tenant, Feature.PDF_EXPORT.value),
        "branding": tenant_has_feature(tenant, Feature.BRANDING.value),
        "whitelabel": tenant_has_feature(tenant, Feature.WHITELABEL.value),
    }


def tenant_feature_ui(tenant: TenantLike | None) -> dict[str, FeatureUI]:
    """
    Richer UI model for templates:
    - enabled flag
    - upgrade_url
    - optional hint (eg "Beschikbaar vanaf Pro")
    """

    out: dict[str, FeatureUI] = {}
    for f in Feature:
        enabled = bool(tenant is not None and tenant_has_feature(tenant, f.value))
        hint = None if enabled else _DEFAULT_HINTS.get(f.value)
        out[f.value] = FeatureUI(enabled=enabled, upgrade_url=_upgrade_url(f.value), hint=hint)
    return out


def tenant_entitlements(tenant: TenantLike | None) -> dict[str, dict[str, object]]:
    """
    Convenience helper for templates:
    High-level entitlement status per action (send quote, export PDF, branding, whitelabel).
    """

    if tenant is None:
        base: dict[str, dict[str, object]] = {}
    else:
        base = {}

    def _wrap(res: EntitlementResult) -> dict[str, object]:
        return {
            "allowed": bool(res.allowed),
            "reason": res.reason,
            "upgrade_url": res.upgrade_url,
        }

    # Even if tenant is None, check_entitlement handles defaults defensively.
    base["send_quote"] = _wrap(check_entitlement(tenant, Action.SEND_QUOTE.value))
    base["export_pdf"] = _wrap(check_entitlement(tenant, Action.EXPORT_PDF.value))
    base["use_branding"] = _wrap(check_entitlement(tenant, Action.USE_BRANDING.value))
    base["use_whitelabel"] = _wrap(check_entitlement(tenant, Action.USE_WHITELABEL.value))

    return base


