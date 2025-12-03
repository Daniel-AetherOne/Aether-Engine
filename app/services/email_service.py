# app/services/email_service.py

import smtplib
from email.message import EmailMessage
from typing import Optional

from app.core.settings import settings


def send_quote_email(
    to_email: str,
    to_name: Optional[str],
    public_url: str,
    lead_id: int,
) -> None:
    """
    Stuur een e-mail naar de klant met de public_url van de offerte.
    Als SMTP niet is geconfigureerd, loggen we de mail alleen naar de console.
    """

    if not to_email:
        # Geen e-mailadres, dan kunnen we niks sturen
        print(f"[email] Geen e-mailadres voor lead {lead_id}, sla e-mail over.")
        return

    subject = f"Je offerte is klaar (lead #{lead_id})"
    display_name = to_name or "klant"

    text_body = (
        f"Beste {display_name},\n\n"
        f"Je offerte is klaar. Je kunt hem hier bekijken:\n"
        f"{public_url}\n\n"
        f"Met vriendelijke groet,\n"
        f"{settings.SMTP_FROM_NAME}"
    )

    html_body = f"""
    <p>Beste {display_name},</p>
    <p>Je offerte is klaar. Je kunt hem hier bekijken:<br>
       <a href="{public_url}">{public_url}</a>
    </p>
    <p>Met vriendelijke groet,<br>
       {settings.SMTP_FROM_NAME}
    </p>
    """

    # Als er geen SMTP-host staat → alleen printen (dev mode)
    if not settings.SMTP_HOST:
        print("=== [DEV EMAIL - GEEN SMTP_HOST] ===")
        print("To:", to_email)
        print("Subject:", subject)
        print(text_body)
        print("=== [/DEV EMAIL] ===")
        return

    msg = EmailMessage()
    from_email = settings.SMTP_FROM_EMAIL or settings.SMTP_USER

    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        server.starttls()
        if settings.SMTP_USER and settings.SMTP_PASSWORD:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.send_message(msg)

    print(f"[email] Offerte-mail verstuurd naar {to_email} voor lead {lead_id}")
