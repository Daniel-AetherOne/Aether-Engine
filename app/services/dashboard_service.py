from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.lead import Lead


SIGNED_STATUSES = {"ACCEPTED", "SIGNED", "COMPLETED", "DONE"}
REJECTED_STATUSES = {"REJECTED", "DECLINED", "CANCELLED"}
PENDING_STATUSES = {"SENT", "VIEWED", "SUCCEEDED"}
NO_RESPONSE_STATUSES = {"SENT", "VIEWED", "PENDING"}


def _to_float(value: object) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _normalize_status(raw_status: str | None) -> str:
    status = (raw_status or "").strip().upper()
    if status in SIGNED_STATUSES:
        return "signed"
    if status in REJECTED_STATUSES:
        return "rejected"
    if status in PENDING_STATUSES:
        return "pending"
    return "other"


def _lead_amount(lead: Lead) -> float:
    # Prefer explicit final_price; fallback to rendered estimate totals.
    final_price = _to_float(getattr(lead, "final_price", None))
    if final_price > 0:
        return final_price

    raw_estimate = getattr(lead, "estimate_json", None)
    if not raw_estimate:
        return 0.0

    try:
        estimate = json.loads(raw_estimate)
    except (TypeError, ValueError, json.JSONDecodeError):
        return 0.0

    totals = estimate.get("totals") if isinstance(estimate, dict) else None
    if not isinstance(totals, dict):
        return 0.0

    return _to_float(totals.get("grand_total") or totals.get("pre_tax"))


def _last_month_keys(count: int, anchor: datetime) -> list[str]:
    year = anchor.year
    month = anchor.month
    keys: list[str] = []
    for _ in range(count):
        keys.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    keys.reverse()
    return keys


def _as_utc(dt_value: datetime | None) -> datetime | None:
    if dt_value is None:
        return None
    if dt_value.tzinfo is None:
        return dt_value.replace(tzinfo=timezone.utc)
    return dt_value.astimezone(timezone.utc)


def get_dashboard_summary(db: Session, tenant_id: str) -> dict:
    leads = db.query(Lead).filter(Lead.tenant_id == tenant_id).all()
    now_utc = datetime.now(timezone.utc)
    overdue_after = now_utc - timedelta(days=14)

    pipeline_value = 0.0
    won_revenue = 0.0

    pending_count = 0
    signed_count = 0
    rejected_count = 0
    overdue_count = 0
    no_response_value = 0.0
    action_needed_today_count = 0

    status_breakdown = {"pending": 0, "signed": 0, "rejected": 0, "other": 0}
    revenue_by_month_map: dict[str, float] = {}
    signed_durations_days: list[float] = []
    time_to_sign_buckets = {
        "0-1_days": 0,
        "2-3_days": 0,
        "4-7_days": 0,
        "8-14_days": 0,
        "15+_days": 0,
    }

    for lead in leads:
        raw_status = (getattr(lead, "status", None) or "").strip().upper()
        status_key = _normalize_status(raw_status)
        status_breakdown[status_key] += 1

        amount = _lead_amount(lead)
        if status_key != "rejected":
            pipeline_value += amount

        if status_key == "signed":
            signed_count += 1
            won_revenue += amount

            accepted_at = getattr(lead, "accepted_at", None)
            if accepted_at:
                month_key = accepted_at.strftime("%Y-%m")
                revenue_by_month_map[month_key] = revenue_by_month_map.get(month_key, 0.0) + amount

            sent_at = getattr(lead, "sent_at", None)
            if accepted_at and sent_at and accepted_at >= sent_at:
                days = (accepted_at - sent_at).total_seconds() / 86400
                signed_durations_days.append(days)
                if days <= 1:
                    time_to_sign_buckets["0-1_days"] += 1
                elif days <= 3:
                    time_to_sign_buckets["2-3_days"] += 1
                elif days <= 7:
                    time_to_sign_buckets["4-7_days"] += 1
                elif days <= 14:
                    time_to_sign_buckets["8-14_days"] += 1
                else:
                    time_to_sign_buckets["15+_days"] += 1
        elif status_key == "pending":
            pending_count += 1
            sent_at = getattr(lead, "sent_at", None)
            if sent_at and sent_at <= overdue_after:
                overdue_count += 1
        elif status_key == "rejected":
            rejected_count += 1

        sent_at_utc = _as_utc(getattr(lead, "sent_at", None))
        created_at_utc = _as_utc(getattr(lead, "created_at", None))
        reference_dt = sent_at_utc or created_at_utc
        if raw_status in NO_RESPONSE_STATUSES and reference_dt and reference_dt <= (
            now_utc - timedelta(days=3)
        ):
            no_response_value += amount
            action_needed_today_count += 1

    closed_count = signed_count + rejected_count
    sign_rate = round((signed_count / closed_count) * 100, 2) if closed_count else 0.0
    avg_time_to_sign_days = (
        round(sum(signed_durations_days) / len(signed_durations_days), 2)
        if signed_durations_days
        else 0.0
    )

    month_keys = _last_month_keys(6, now_utc)
    revenue_by_month = [
        {"month": month, "value": round(revenue_by_month_map.get(month, 0.0), 2)}
        for month in month_keys
    ]

    return {
        "kpis": {
            "pipeline_value": round(pipeline_value, 2),
            "won_revenue": round(won_revenue, 2),
            "pending_count": pending_count,
            "signed_count": signed_count,
            "rejected_count": rejected_count,
            "overdue_count": overdue_count,
            "no_response_value": round(no_response_value, 2),
            "action_needed_today_count": action_needed_today_count,
            "sign_rate": sign_rate,
            "avg_time_to_sign_days": avg_time_to_sign_days,
        },
        "revenue_by_month": revenue_by_month,
        "status_breakdown": status_breakdown,
        "time_to_sign_buckets": time_to_sign_buckets,
    }
