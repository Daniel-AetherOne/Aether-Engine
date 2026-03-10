# app/services/email_service.py
from __future__ import annotations

import os
import httpx
from typing import Any

POSTMARK_API_URL = "https://api.postmarkapp.com/email"


class EmailSendError(Exception):
    pass


def is_email_enabled() -> bool:
    return os.getenv("EMAIL_ENABLED", "false").lower() == "true"


async def send_email(
    *,
    to: str,
    subject: str,
    html_body: str,
    text_body: str,
    tag: str | None = None,
    reply_to: str | None = None,
    metadata: dict[str, str] | None = None,
) -> dict[str, Any]:
    server_token = os.getenv("POSTMARK_SERVER_TOKEN", "").strip()
    from_email = os.getenv("POSTMARK_FROM_EMAIL", "").strip()
    from_name = os.getenv("POSTMARK_FROM_NAME", "Paintly").strip()
    message_stream = os.getenv("POSTMARK_MESSAGE_STREAM", "outbound").strip()

    if not is_email_enabled():
        return {"ok": False, "skipped": True, "reason": "EMAIL_ENABLED=false"}

    if not server_token:
        raise EmailSendError("POSTMARK_SERVER_TOKEN ontbreekt")
    if not from_email:
        raise EmailSendError("POSTMARK_FROM_EMAIL ontbreekt")

    payload = {
        "From": f"{from_name} <{from_email}>",
        "To": to,
        "Subject": subject,
        "HtmlBody": html_body,
        "TextBody": text_body,
        "MessageStream": message_stream,
        "TrackOpens": True,
        "Tag": tag,
        "ReplyTo": reply_to,
        "Metadata": metadata or {},
    }

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Postmark-Server-Token": server_token,
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(POSTMARK_API_URL, headers=headers, json=payload)

    # HTTP errors eerst
    response.raise_for_status()

    data = response.json()

    # Postmark kan functioneel falen via ErrorCode in body
    error_code = data.get("ErrorCode", -1)
    if error_code != 0:
        raise EmailSendError(
            f"Postmark send mislukt: ErrorCode={error_code}, Message={data.get('Message')}"
        )

    return {"ok": True, "provider": "postmark", "response": data}
