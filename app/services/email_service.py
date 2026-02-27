# app/services/email_service.py

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional, Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from postmarker.core import PostmarkClient  # pip install postmarker

from app.core.settings import settings

logger = logging.getLogger(__name__)


class EmailService:
    def __init__(self) -> None:
        self.enabled = bool(getattr(settings, "EMAILS_ENABLED", True))
        self.server_token = getattr(settings, "POSTMARK_SERVER_TOKEN", "")
        self.message_stream = getattr(
            settings, "POSTMARK_MESSAGE_STREAM", "transactional"
        )
        self.from_email = getattr(
            settings, "POSTMARK_FROM_EMAIL", "Paintly <info@getpaintly.com>"
        )
        self.reply_to_default = getattr(settings, "POSTMARK_REPLY_TO", None)

        if self.enabled and not self.server_token:
            raise RuntimeError(
                "POSTMARK_SERVER_TOKEN ontbreekt terwijl EMAILS_ENABLED=true"
            )

        # templates/emails/...
        templates_dir = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                "..",
                "verticals",
                "paintly",
                "templates",
                "email",
            )
        )
        self.jinja = Environment(
            loader=FileSystemLoader(templates_dir),
            autoescape=select_autoescape(["html", "xml"]),
        )

        self.client = PostmarkClient(server_token=self.server_token)

    def render(self, template_name: str, **ctx: Any) -> str:
        return self.jinja.get_template(template_name).render(**ctx)

    async def send_email(
        self,
        *,
        to: str,
        subject: str,
        html_body: str,
        text_body: Optional[str] = None,
        reply_to: Optional[str] = None,
        tag: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
        message_stream: Optional[str] = None,
    ) -> bool:
        """
        Best-effort: return True/False. No raise (pipeline-safe).
        """
        if not self.enabled:
            logger.info("Emails disabled; skip to=%s subject=%s", to, subject)
            return True

        payload: dict[str, Any] = {
            "From": self.from_email,
            "To": to,
            "Subject": subject,
            "HtmlBody": html_body,
        }
        if text_body:
            payload["TextBody"] = text_body
        if reply_to or self.reply_to_default:
            payload["ReplyTo"] = reply_to or self.reply_to_default
        if tag:
            payload["Tag"] = tag
        if metadata:
            payload["Metadata"] = metadata

        try:
            # Postmarker is sync → run in thread
            result = await asyncio.to_thread(self.client.emails.send, **payload)
            logger.info("Postmark sent to=%s subject=%s result=%s", to, subject, result)
            return True
        except Exception as e:
            logger.exception(
                "Postmark send failed to=%s subject=%s err=%s", to, subject, e
            )
            return False

    # ---- Event helpers ----

    async def send_lead_notification(
        self,
        *,
        painter_email: str,
        tenant_name: str,
        lead_id: int | str,
        lead_name: str,
        lead_email: str,
        admin_url: Optional[str] = None,
    ) -> bool:
        subject = f"Nieuwe lead: {lead_name}"
        html = self.render(
            "lead_notification.html",
            tenant_name=tenant_name,
            lead_id=lead_id,
            lead_name=lead_name,
            lead_email=lead_email,
            admin_url=admin_url,
        )
        text = f"Nieuwe lead: {lead_name} ({lead_email}) — lead_id={lead_id}"
        return await self.send_email(
            to=painter_email,
            subject=subject,
            html_body=html,
            text_body=text,
            tag="new_lead",
            metadata={"lead_id": str(lead_id)},
        )

    async def send_quote_ready(
        self,
        *,
        lead_email: str,
        lead_name: str,
        tenant_name: str,
        quote_url: str,
        lead_id: int | str,
        tenant_reply_to: Optional[str] = None,
    ) -> bool:
        subject = f"Je offerte van {tenant_name} staat klaar"
        html = self.render(
            "estimate_ready.html",
            lead_name=lead_name,
            tenant_name=tenant_name,
            quote_url=quote_url,
        )
        text = f"Hoi {lead_name}, je offerte staat klaar: {quote_url}"
        return await self.send_email(
            to=lead_email,
            subject=subject,
            html_body=html,
            text_body=text,
            reply_to=tenant_reply_to,
            tag="quote_ready",
            metadata={"lead_id": str(lead_id)},
        )

    async def send_quote_accepted(
        self,
        *,
        painter_email: str,
        tenant_name: str,
        lead_id: int | str,
        lead_name: str,
        lead_email: str,
        quote_url: Optional[str] = None,
        admin_url: Optional[str] = None,
    ) -> bool:
        subject = f"Offerte geaccepteerd: {lead_name}"
        html = self.render(
            "estimate_accepted.html",
            tenant_name=tenant_name,
            lead_id=lead_id,
            lead_name=lead_name,
            lead_email=lead_email,
            quote_url=quote_url,
            admin_url=admin_url,
        )
        text = (
            f"Offerte geaccepteerd door {lead_name} ({lead_email}) — lead_id={lead_id}"
        )
        return await self.send_email(
            to=painter_email,
            subject=subject,
            html_body=html,
            text_body=text,
            tag="quote_accepted",
            metadata={"lead_id": str(lead_id)},
        )
