# scripts/seed_scheduled.py
from __future__ import annotations

import secrets
from datetime import datetime, timezone, timedelta

from zoneinfo import ZoneInfo

from app.db import SessionLocal
from app.models.lead import Lead
from app.models.job import Job
from app.models.user import User


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_user_and_tenant(db) -> tuple[User, str]:
    u = db.query(User).first()
    if not u:
        raise RuntimeError("No users found. Run: python -m scripts.bootstrap_dev_auth")
    return u, str(u.tenant_id)


def safe_tz(tz_name: str | None) -> str:
    tz = (tz_name or "").strip()
    if not tz:
        return "America/New_York"
    try:
        ZoneInfo(tz)
        return tz
    except Exception:
        return "America/New_York"


def local_to_utc(dt_local_naive: datetime, tz_name: str) -> datetime:
    tz = ZoneInfo(tz_name)
    dt_local = dt_local_naive.replace(tzinfo=tz)
    return dt_local.astimezone(timezone.utc)


def main():
    db = SessionLocal()
    try:
        user, tenant_id = get_user_and_tenant(db)
        tz_name = safe_tz(getattr(user, "timezone", None))

        # 1) reset tenant-scoped
        deleted_jobs = (
            db.query(Job)
            .filter(Job.tenant_id == tenant_id)
            .delete(synchronize_session=False)
        )
        deleted_leads = (
            db.query(Lead)
            .filter(Lead.tenant_id == tenant_id)
            .delete(synchronize_session=False)
        )
        db.commit()
        print(
            f"🧹 Reset tenant={tenant_id}: deleted jobs={deleted_jobs}, leads={deleted_leads}"
        )
        print(f"🕒 Using timezone: {tz_name}")

        # 2) seed leads
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

        # 3) job NEW (unscheduled)
        job_new = Job(
            tenant_id=tenant_id,
            lead_id=lead_accepted.id,
            status="NEW",
        )
        db.add(job_new)
        db.commit()

        # 4) another accepted lead + scheduled job (tomorrow 09:00 local)
        lead_accepted2 = Lead(
            tenant_id=tenant_id,
            name="Emily Carter",
            email="emily@example.com",
            phone="+1 555-0104",
            notes="Kitchen cabinets repaint (accepted)",
            status="ACCEPTED",
            sent_at=utcnow(),
            public_token=secrets.token_hex(16),
            estimate_html_key="dev/estimate_accepted2.html",
        )
        db.add(lead_accepted2)
        db.commit()

        tz = ZoneInfo(tz_name)
        tomorrow_local_date = datetime.now(tz).date() + timedelta(days=1)
        dt_local_naive = datetime.strptime(
            f"{tomorrow_local_date.isoformat()}T09:00", "%Y-%m-%dT%H:%M"
        )
        dt_utc = local_to_utc(dt_local_naive, tz_name)

        job_scheduled = Job(
            tenant_id=tenant_id,
            lead_id=lead_accepted2.id,
            status="SCHEDULED",
            scheduled_at=dt_utc,
            scheduled_tz=tz_name,
        )
        db.add(job_scheduled)
        db.commit()

        print("✅ Seed scheduled done")
        print("TENANT_ID:", tenant_id)
        print("User:", user.email, "tz:", tz_name)
        print("Lead SENT:", lead_sent.id)
        print("Lead VIEWED:", lead_viewed.id)
        print("Lead ACCEPTED:", lead_accepted.id, "-> Job NEW:", job_new.id)
        print(
            "Lead ACCEPTED2:",
            lead_accepted2.id,
            "-> Job SCHEDULED:",
            job_scheduled.id,
            "UTC:",
            job_scheduled.scheduled_at,
        )

    finally:
        db.close()


if __name__ == "__main__":
    main()
