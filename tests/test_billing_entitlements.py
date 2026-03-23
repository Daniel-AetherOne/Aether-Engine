from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.billing.entitlements import Action, EntitlementResult, check_entitlement
from app.billing.features import Feature


@dataclass(frozen=True)
class TenantStub:
    plan_code: str | None
    subscription_status: str | None
    quotes_sent: int | None = None
    quote_limit: int | None = None


@pytest.mark.parametrize(
    "plan_code",
    ["starter_99", "pro_199", "business_399"],
)
def test_send_quote_allowed_under_limit_for_paid_plans(plan_code: str) -> None:
    tenant = TenantStub(
        plan_code=plan_code,
        subscription_status="active",
        quotes_sent=5,
        quote_limit=10,
    )

    res = check_entitlement(tenant, Action.SEND_QUOTE.value)
    assert isinstance(res, EntitlementResult)
    assert res.allowed is True
    assert res.reason is None
    assert res.feature == Feature.BASIC_SENDING.value


@pytest.mark.parametrize(
    "subscription_status",
    ["inactive", "past_due", "canceled", None, ""],
)
def test_send_quote_denied_for_inactive_subscription(subscription_status: str | None) -> None:
    tenant = TenantStub(
        plan_code="pro_199",
        subscription_status=subscription_status,
        quotes_sent=0,
        quote_limit=10,
    )

    res = check_entitlement(tenant, Action.SEND_QUOTE.value)
    assert res.allowed is False
    assert res.reason == "subscription_inactive"


def test_send_quote_denied_when_usage_limit_reached() -> None:
    tenant = TenantStub(
        plan_code="pro_199",
        subscription_status="active",
        quotes_sent=10,
        quote_limit=10,
    )

    res = check_entitlement(tenant, Action.SEND_QUOTE.value)
    assert res.allowed is False
    assert res.reason == "usage_limit_reached"
    assert res.usage_limit == 10
    assert res.usage_current == 10


@pytest.mark.parametrize("plan_code", [None, "", "unknown_plan"])
def test_send_quote_denied_for_unknown_or_none_plan(plan_code: str | None) -> None:
    tenant = TenantStub(
        plan_code=plan_code,
        subscription_status="active",
        quotes_sent=0,
        quote_limit=10,
    )

    res = check_entitlement(tenant, Action.SEND_QUOTE.value)
    assert res.allowed is False
    assert res.reason == "feature_not_in_plan"
    assert res.feature == Feature.BASIC_SENDING.value


@pytest.mark.parametrize(
    "plan_code, expected_allowed",
    [
        ("starter_99", True),
        ("pro_199", True),
        ("business_399", True),
    ],
)
def test_export_pdf_entitlement(plan_code: str, expected_allowed: bool) -> None:
    tenant = TenantStub(plan_code=plan_code, subscription_status="active")

    res = check_entitlement(tenant, Action.EXPORT_PDF.value)
    assert res.allowed is expected_allowed
    assert res.feature == Feature.PDF_EXPORT.value
    if not expected_allowed:
        assert res.reason in {"subscription_inactive", "feature_not_in_plan"}


@pytest.mark.parametrize(
    "plan_code, expected_allowed",
    [
        ("starter_99", False),
        ("pro_199", True),
        ("business_399", True),
    ],
)
def test_use_branding_entitlement(plan_code: str, expected_allowed: bool) -> None:
    tenant = TenantStub(plan_code=plan_code, subscription_status="active")

    res = check_entitlement(tenant, Action.USE_BRANDING.value)
    assert res.allowed is expected_allowed
    assert res.feature == Feature.BRANDING.value
    if not expected_allowed:
        assert res.reason in {"subscription_inactive", "feature_not_in_plan"}


@pytest.mark.parametrize(
    "plan_code, expected_allowed",
    [
        ("starter_99", False),
        ("pro_199", False),
        ("business_399", True),
    ],
)
def test_use_whitelabel_entitlement(plan_code: str, expected_allowed: bool) -> None:
    tenant = TenantStub(plan_code=plan_code, subscription_status="active")

    res = check_entitlement(tenant, Action.USE_WHITELABEL.value)
    assert res.allowed is expected_allowed
    assert res.feature == Feature.WHITELABEL.value
    if not expected_allowed:
        assert res.reason in {"subscription_inactive", "feature_not_in_plan"}


def test_unknown_action_denied() -> None:
    tenant = TenantStub(plan_code="pro_199", subscription_status="active")

    res = check_entitlement(tenant, "DOES_NOT_EXIST")
    assert res.allowed is False
    assert res.reason == "unknown_action"
    assert res.action == "DOES_NOT_EXIST"

