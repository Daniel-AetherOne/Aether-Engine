# scripts/seed_everything.py
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4
import secrets
from sqlalchemy import text

from app.db import SessionLocal
from app.models.lead import Lead
from app.models.job import Job
from app.services.storage import get_storage, put_text


def utcnow():
    return datetime.now(timezone.utc)


def set_if_column(model_cls, obj, field: str, value):
    # Alleen setten als de kolom echt bestaat op het SQLAlchemy model
    if hasattr(model_cls, field):
        setattr(obj, field, value)


def main():
    db = SessionLocal()

    # pak tenant (na /auth/register bestaat die)
    tenant_id = db.execute(text("select id from tenants limit 1")).scalar()
    if not tenant_id:
        print("❌ No tenant found. Maak eerst een account via /auth/register.")
        return

    tenant_id = str(tenant_id)
    print("✅ Using tenant:", tenant_id)

    storage = get_storage()
    today = utcnow().date().isoformat()

    # helper om dummy estimate te maken + in storage te zetten
    def create_estimate_html_for_lead(lead_id: int) -> str:
        estimate_key = (
            f"leads/{lead_id}/estimates/{today}/estimate_{lead_id}_{uuid4().hex}.html"
        )

        html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Estimate #{lead_id}</title></head>
<body style="font-family:system-ui;max-width:900px;margin:40px auto;line-height:1.4">
  <h1>Paintly Estimate</h1>
  <p><strong>Lead:</strong> {lead_id}</p>
  <p>This is seeded dummy HTML to test Open estimate / Public estimate flow.</p>
  <hr/>
  <h3>Total</h3>
  <p>$ 2,450.00</p>
</body></html>
"""
        # tenant-aware opslaan (S3Storage doet tenant_id prefix)
        put_text(
            storage,
            tenant_id=tenant_id,
            key=estimate_key,
            text=html,
            content_type="text/html; charset=utf-8",
        )
        return estimate_key

    # ---- Maak 6 leads met “realistische” mix ----
    # NEW (geen estimate)
    l_new = Lead(
        tenant_id=tenant_id,
        vertical="painters_us",
        name="Seed Lead NEW",
        email="new@example.com",
        phone="555-0101",
        notes="New lead - no estimate yet",
        status="NEW",
    )
    db.add(l_new)
    db.flush()

    # SUCCEEDED-ish (heeft estimate_html_key maar nog niet sent)
    l_ready = Lead(
        tenant_id=tenant_id,
        vertical="painters_us",
        name="Seed Lead READY",
        email="ready@example.com",
        phone="555-0102",
        notes="Estimate ready - internal open estimate test",
        status="NEW",
    )
    db.add(l_ready)
    db.flush()
    l_ready.estimate_html_key = create_estimate_html_for_lead(l_ready.id)

    # SENT (public token + sent_at)
    l_sent = Lead(
        tenant_id=tenant_id,
        vertical="painters_us",
        name="Seed Lead SENT",
        email="sent@example.com",
        phone="555-0103",
        notes="Sent lead - open public URL should show accept bar",
        status="SENT",
    )
    db.add(l_sent)
    db.flush()
    l_sent.estimate_html_key = create_estimate_html_for_lead(l_sent.id)
    set_if_column(Lead, l_sent, "public_token", secrets.token_hex(16))
    set_if_column(Lead, l_sent, "sent_at", utcnow())

    # VIEWED (viewed_at)
    l_viewed = Lead(
        tenant_id=tenant_id,
        vertical="painters_us",
        name="Seed Lead VIEWED",
        email="viewed@example.com",
        phone="555-0104",
        notes="Viewed lead - public page already viewed",
        status="VIEWED",
    )
    db.add(l_viewed)
    db.flush()
    l_viewed.estimate_html_key = create_estimate_html_for_lead(l_viewed.id)
    set_if_column(Lead, l_viewed, "public_token", secrets.token_hex(16))
    set_if_column(Lead, l_viewed, "sent_at", utcnow())
    set_if_column(Lead, l_viewed, "viewed_at", utcnow())

    # ACCEPTED + Job NEW
    l_acc = Lead(
        tenant_id=tenant_id,
        vertical="painters_us",
        name="Seed Lead ACCEPTED",
        email="accepted@example.com",
        phone="555-0105",
        notes="Accepted lead - should have a Job NEW",
        status="ACCEPTED",
    )
    db.add(l_acc)
    db.flush()
    l_acc.estimate_html_key = create_estimate_html_for_lead(l_acc.id)
    set_if_column(Lead, l_acc, "public_token", secrets.token_hex(16))
    set_if_column(Lead, l_acc, "accepted_at", utcnow())

    job_new = Job(
        tenant_id=tenant_id,
        lead_id=l_acc.id,
        status="NEW",
    )
    db.add(job_new)

    # ACCEPTED + Job DONE (dashboard DONE count test)
    l_done = Lead(
        tenant_id=tenant_id,
        vertical="painters_us",
        name="Seed Lead DONE",
        email="done@example.com",
        phone="555-0106",
        notes="Accepted + job DONE - dashboard test",
        status="ACCEPTED",
    )
    db.add(l_done)
    db.flush()
    l_done.estimate_html_key = create_estimate_html_for_lead(l_done.id)
    set_if_column(Lead, l_done, "public_token", secrets.token_hex(16))
    set_if_column(Lead, l_done, "accepted_at", utcnow())

    job_done = Job(
        tenant_id=tenant_id,
        lead_id=l_done.id,
        status="DONE",
    )
    # timestamps (alleen als kolommen bestaan)
    set_if_column(Job, job_done, "scheduled_at", utcnow())
    set_if_column(Job, job_done, "started_at", utcnow())
    set_if_column(Job, job_done, "done_at", utcnow())
    db.add(job_done)

    db.commit()

    print("✅ Seed complete.")
    print("Open:")
    print(" - /app/leads")
    print(" - /app/jobs")
    print("Public URLs:")
    if hasattr(Lead, "public_token"):
        print(f" - SENT:    /e/{l_sent.public_token}")
        print(f" - VIEWED:  /e/{l_viewed.public_token}")
        print(f" - ACCEPTED:/e/{l_acc.public_token}")


if __name__ == "__main__":
    main()
