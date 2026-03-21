from __future__ import annotations

from typing import Any

from app.verticals.paintly.calendar_ics import QuoteCalendarPayload


def build_google_event_payload(quote_event: QuoteCalendarPayload) -> dict[str, Any]:
    return {
        "summary": quote_event.summary,
        "description": quote_event.description,
        "location": quote_event.location or None,
        "start": {"dateTime": quote_event.starts_at.isoformat(), "timeZone": "UTC"},
        "end": {"dateTime": quote_event.ends_at.isoformat(), "timeZone": "UTC"},
        "attendees": (
            [{"email": quote_event.customer_email}]
            if quote_event.customer_email
            else []
        ),
    }
