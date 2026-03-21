from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from app.models.lead import Lead


@dataclass(frozen=True)
class QuoteCalendarPayload:
    quote_id: str
    tenant_id: str
    customer_name: str
    customer_email: str
    summary: str
    description: str
    location: str
    starts_at: datetime
    ends_at: datetime
    uid: str
    created_at: datetime


def _normalize_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _ics_escape(value: str) -> str:
    escaped = (value or "").replace("\\", "\\\\")
    escaped = escaped.replace("\n", "\\n")
    escaped = escaped.replace(",", "\\,")
    escaped = escaped.replace(";", "\\;")
    return escaped


def _fmt_ics_dt(value: datetime) -> str:
    return _normalize_utc(value).strftime("%Y%m%dT%H%M%SZ")


def _build_location_from_intake(raw_intake_payload: str | None) -> str:
    if not raw_intake_payload:
        return ""
    try:
        payload = json.loads(raw_intake_payload)
    except Exception:
        return ""
    if not isinstance(payload, dict):
        return ""

    street = str(payload.get("street") or payload.get("address_street") or "").strip()
    city = str(payload.get("city") or payload.get("address_city") or "").strip()
    state = str(payload.get("state") or payload.get("region") or "").strip()
    zip_code = str(payload.get("zip") or payload.get("postal_code") or "").strip()
    country = str(payload.get("country") or "").strip()
    parts = [p for p in (street, city, state, zip_code, country) if p]
    return ", ".join(parts)


def build_quote_calendar_payload(lead: Lead) -> QuoteCalendarPayload:
    status = str(getattr(lead, "status", "") or "").upper().strip()
    if status != "ACCEPTED":
        raise ValueError("Only accepted quotes can be exported to calendar.")

    starts_at = getattr(lead, "scheduled_start", None)
    ends_at = getattr(lead, "scheduled_end", None)
    if not starts_at or not ends_at:
        raise ValueError("Quote schedule is missing.")

    starts_at = _normalize_utc(starts_at)
    ends_at = _normalize_utc(ends_at)
    if ends_at <= starts_at:
        raise ValueError("Quote schedule end must be after schedule start.")

    quote_id = str(lead.id)
    tenant_id = str(getattr(lead, "tenant_id", "") or "default")
    customer_name = str(getattr(lead, "name", "") or "").strip()
    customer_email = str(getattr(lead, "email", "") or "").strip()
    location = str(getattr(lead, "address_line", "") or "").strip()
    if not location:
        location = _build_location_from_intake(getattr(lead, "intake_payload", None))
    summary = f"Paintly job - {customer_name or 'Accepted quote'}"
    description = f"Accepted Paintly quote {quote_id}"
    if customer_email:
        description = f"{description} for {customer_email}"
    uid = f"paintly-quote-{tenant_id}-{quote_id}@paintly.local"

    created_at = getattr(lead, "created_at", None) or datetime.now(UTC)
    created_at = _normalize_utc(created_at)

    return QuoteCalendarPayload(
        quote_id=quote_id,
        tenant_id=tenant_id,
        customer_name=customer_name,
        customer_email=customer_email,
        summary=summary,
        description=description,
        location=location,
        starts_at=starts_at,
        ends_at=ends_at,
        uid=uid,
        created_at=created_at,
    )


def build_quote_ics(payload: QuoteCalendarPayload) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Paintly//Quote Calendar//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{_ics_escape(payload.uid)}",
        f"DTSTAMP:{_fmt_ics_dt(datetime.now(UTC))}",
        f"CREATED:{_fmt_ics_dt(payload.created_at)}",
        f"DTSTART:{_fmt_ics_dt(payload.starts_at)}",
        f"DTEND:{_fmt_ics_dt(payload.ends_at)}",
        f"SUMMARY:{_ics_escape(payload.summary)}",
        f"DESCRIPTION:{_ics_escape(payload.description)}",
    ]
    if payload.location:
        lines.append(f"LOCATION:{_ics_escape(payload.location)}")
    lines.extend(["END:VEVENT", "END:VCALENDAR"])
    return "\r\n".join(lines) + "\r\n"


def build_quote_ics_filename(quote_id: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "-", str(quote_id))
    return f"quote-{cleaned}.ics"
