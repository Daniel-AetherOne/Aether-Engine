# app/services/email.py
from __future__ import annotations

import json
import logging
from typing import Optional, Dict, Any

import requests

from app.core.settings import settings

logger = logging.getLogger(__name__)

POSTMARK_SEND_URL = "https://api.postmarkapp.com/email"


class EmailError(RuntimeError):
    pass


def send_postmark_email(
    *,
    to: str,
    subject: str,
    html_body: str,
    text_body: Optional[str] = None,
    message_stream: str = "outbound",  # Postmark default stream
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Returns Postmark MessageID on success.
    Raises EmailError on failure.
    """
    if not settings.POSTMARK_SERVER_TOKEN:
        raise EmailError("postmark_not_configured: POSTMARK_SERVER_TOKEN missing")
    if not settings.POSTMARK_FROM:
        raise EmailError("postmark_not_configured: POSTMARK_FROM missing")

    payload: Dict[str, Any] = {
        "From": settings.POSTMARK_FROM,
        "To": to,
        "Subject": subject,
        "HtmlBody": html_body,
        "MessageStream": message_stream,
    }
    if settings.POSTMARK_REPLY_TO:
        payload["ReplyTo"] = settings.POSTMARK_REPLY_TO
    if text_body:
        payload["TextBody"] = text_body
    if metadata:
        payload["Metadata"] = metadata

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Postmark-Server-Token": settings.POSTMARK_SERVER_TOKEN,
    }

    try:
        r = requests.post(
            POSTMARK_SEND_URL,
            headers=headers,
            data=json.dumps(payload),
            timeout=15,
        )
    except Exception as e:
        raise EmailError(f"postmark_network_error:{type(e).__name__}:{e}")

    if r.status_code >= 300:
        # Postmark returns JSON with Message/ErrorCode
        try:
            data = r.json()
        except Exception:
            data = {"raw": r.text}
        raise EmailError(f"postmark_send_failed:{r.status_code}:{data}")

    data = r.json()
    message_id = str(data.get("MessageID") or "")
    if not message_id:
        raise EmailError(f"postmark_send_failed:no_message_id:{data}")

    return message_id
