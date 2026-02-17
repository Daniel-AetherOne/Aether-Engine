# scripts/seed_reset.py
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from app.db import SessionLocal
from app.models.lead import Lead
from app.models.job import Job
from app.models.user import User


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_tenant_id(db) -> str:
    u = db.query(User).first()
    if not u:
        raise RuntimeError("No users found. Run: python -m scripts.bootstrap_dev_auth")
    return str(u.tenant_id)


def main():
    db = SessionLocal()
    try:
        tenant_id = get_tenant_id(db)

        # 1) delete jobs for this tenant
        deleted_jobs = (
            db.query(Job)
            .filter(Job.tenant_id == tenant_id)
            .delete(synchronize_session=False)
        )

        # 2) delete leads for this tenant
        deleted_leads = (
            db.query(Lead)
            .filter(Lead.tenant_id == tenant_id)
            .delete(synchronize_session=False)
        )

        db.commit()
        print(
            f"🧹 Reset tenant={tenant_id}: deleted jobs={deleted_jobs}, leads={deleted_leads}"
        )

        # 3) seed leads
        lead_sent = Lead(
            tenant_id=tenant_id,
            name="John Doe",
            email="john@example.com",
            phone="+1 555-0101",
            notes="Interior repaint - 2 bedrooms",
            status="SENT",
            sent_at=utcnow(),
            public_token=secrets.token_hex(16),
            estimate_html_key="dev/estimate_sent.html",
        )

        lead_viewed = Lead(
            tenant_id=tenant_id,
            name="Sarah Smith",
            email="sarah@example.com",
            phone="+1 555-0102",
            notes="Exterior trim + fascia",
            status="VIEWED",
            sent_at=utcnow(),
            public_token=secrets.token_hex(16),
            estimate_html_key="dev/estimate_viewed.html",
        )

        lead_accepted = Lead(
            tenant_id=tenant_id,
            name="Mike Johnson",
            email="mike@example.com",
            phone="+1 555-0103",
            notes="Full house repaint, estimate accepted",
            status="ACCEPTED",
            sent_at=utcnow(),
            public_token=secrets.token_hex(16),
            estimate_html_key="dev/estimate_accepted.html",
        )

        db.add_all([lead_sent, lead_viewed, lead_accepted])
        db.commit()

        # 4) seed job for accepted lead
        job = Job(
            tenant_id=tenant_id,
            lead_id=lead_accepted.id,
            status="NEW",
        )
        db.add(job)
        db.commit()

        print("✅ Seed done")
        print("TENANT_ID:", tenant_id)
        print("Lead SENT:", lead_sent.id)
        print("Lead VIEWED:", lead_viewed.id)
        print("Lead ACCEPTED:", lead_accepted.id)
        print("Job:", job.id)

    finally:
        db.close()


if __name__ == "__main__":
    main()
