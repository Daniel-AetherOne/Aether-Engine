from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.billing.features import (
    Feature,
    get_plan_features,
    is_subscription_accessible,
    plan_supports_feature,
    tenant_has_feature,
)


@dataclass(frozen=True)
class TenantStub:
    plan_code: str | None
    subscription_status: str | None


@pytest.mark.parametrize(
    "plan_code, expected",
    [
        (
            "starter_99",
            {
                Feature.BASIC_SENDING.value,
            },
        ),
        (
            "pro_199",
            {
                Feature.BASIC_SENDING.value,
                Feature.PDF_EXPORT.value,
                Feature.BRANDING.value,
            },
        ),
        (
            "business_399",
            {
                Feature.BASIC_SENDING.value,
                Feature.PDF_EXPORT.value,
                Feature.BRANDING.value,
                Feature.WHITELABEL.value,
            },
        ),
    ],
)
def test_get_plan_features_known_plans(plan_code: str, expected: set[str]) -> None:
    assert get_plan_features(plan_code) == expected


@pytest.mark.parametrize("plan_code", [None, "", "unknown_plan", "starter_999"])
def test_get_plan_features_unknown_or_none(plan_code: str | None) -> None:
    assert get_plan_features(plan_code) == set()


def test_plan_matrix_starter_99() -> None:
    assert plan_supports_feature("starter_99", Feature.BASIC_SENDING.value) is True
    assert plan_supports_feature("starter_99", Feature.PDF_EXPORT.value) is False
    assert plan_supports_feature("starter_99", Feature.BRANDING.value) is False
    assert plan_supports_feature("starter_99", Feature.WHITELABEL.value) is False


def test_plan_matrix_pro_199() -> None:
    assert plan_supports_feature("pro_199", Feature.BASIC_SENDING.value) is True
    assert plan_supports_feature("pro_199", Feature.PDF_EXPORT.value) is True
    assert plan_supports_feature("pro_199", Feature.BRANDING.value) is True
    assert plan_supports_feature("pro_199", Feature.WHITELABEL.value) is False


def test_plan_matrix_business_399() -> None:
    assert plan_supports_feature("business_399", Feature.BASIC_SENDING.value) is True
    assert plan_supports_feature("business_399", Feature.PDF_EXPORT.value) is True
    assert plan_supports_feature("business_399", Feature.BRANDING.value) is True
    assert plan_supports_feature("business_399", Feature.WHITELABEL.value) is True


@pytest.mark.parametrize(
    "subscription_status, expected",
    [
        ("active", True),
        ("trialing", True),
        ("canceled", False),
        ("past_due", False),
        ("inactive", False),
        (None, False),
        ("", False),
        ("weird_status", False),
    ],
)
def test_is_subscription_accessible(subscription_status: str | None, expected: bool) -> None:
    assert is_subscription_accessible(subscription_status) is expected


def test_tenant_has_feature_requires_accessible_subscription() -> None:
    # active + feature present => True
    t_active = TenantStub(plan_code="pro_199", subscription_status="active")
    assert tenant_has_feature(t_active, Feature.PDF_EXPORT.value) is True

    # trialing + feature present => True
    t_trial = TenantStub(plan_code="pro_199", subscription_status="trialing")
    assert tenant_has_feature(t_trial, Feature.PDF_EXPORT.value) is True

    # canceled => False, even if plan includes it
    t_canceled = TenantStub(plan_code="business_399", subscription_status="canceled")
    assert tenant_has_feature(t_canceled, Feature.WHITELABEL.value) is False

    # past_due => False
    t_past_due = TenantStub(plan_code="business_399", subscription_status="past_due")
    assert tenant_has_feature(t_past_due, Feature.WHITELABEL.value) is False

    # inactive => False
    t_inactive = TenantStub(plan_code="business_399", subscription_status="inactive")
    assert tenant_has_feature(t_inactive, Feature.WHITELABEL.value) is False

    # None => False
    t_none = TenantStub(plan_code="business_399", subscription_status=None)
    assert tenant_has_feature(t_none, Feature.WHITELABEL.value) is False


def test_unknown_plan_code_has_no_features() -> None:
    t = TenantStub(plan_code="unknown_plan", subscription_status="active")
    assert tenant_has_feature(t, Feature.BASIC_SENDING.value) is False
    assert tenant_has_feature(t, Feature.PDF_EXPORT.value) is False
    assert tenant_has_feature(t, Feature.BRANDING.value) is False
    assert tenant_has_feature(t, Feature.WHITELABEL.value) is False

