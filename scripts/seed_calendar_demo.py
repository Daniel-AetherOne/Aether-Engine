# scripts/seed_calendar_demo.py
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import secrets

from app.db import SessionLocal
from app.models.user import User
from app.models.lead import Lead
from app.models.job import Job


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _make_local_dt(
    tz: ZoneInfo, days_from_today: int, hour: int, minute: int
) -> datetime:
    now_local = datetime.now(tz)
    d = now_local.date() + timedelta(days=days_from_today)
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=tz)


def _create_lead(db, tenant_id: str, name: str, notes: str, status: str) -> Lead:
    # Keep this minimal to avoid mismatches with your Lead model.
    lead = Lead(
        tenant_id=tenant_id,
        name=name,
        notes=notes,
        status=status,
    )

    # Optional fields if they exist on your Lead model (safe-ish)
    if hasattr(lead, "email"):
        lead.email = (
            f"{name.lower().replace(' ', '.')}{secrets.randbelow(999)}@example.com"
        )
    if hasattr(lead, "estimate_html_key"):
        lead.estimate_html_key = "dev/estimate_demo.html"
    if hasattr(lead, "public_token"):
        lead.public_token = secrets.token_hex(12)

    db.add(lead)
    db.flush()  # ensures lead.id is available
    return lead


def _create_job(
    db,
    tenant_id: str,
    lead_id: int,
    status: str,
    scheduled_at_utc: datetime | None,
    tz_name: str,
):
    job = Job(
        tenant_id=tenant_id,
        lead_id=lead_id,
        status=status,
        scheduled_at=scheduled_at_utc,
    )

    # Only set scheduled_tz if your model has it
    if hasattr(job, "scheduled_tz"):
        job.scheduled_tz = tz_name

    db.add(job)
    db.flush()
    return job


def main():
    db = SessionLocal()
    try:
        user = db.query(User).first()
        if not user:
            raise RuntimeError(
                "No users found. Create/login a user first, then run this seed."
            )

        tenant_id = str(user.tenant_id)
        tz_name = getattr(user, "timezone", None) or "America/New_York"
        tz = ZoneInfo(tz_name)

        # ---- Create 2 UNSCHEDULED jobs (NEW + scheduled_at=None)
        l1 = _create_lead(
            db,
            tenant_id,
            name="Alex Rivera",
            notes="Interior repaint quote follow-up (unscheduled)",
            status="ACCEPTED",
        )
        _create_job(
            db, tenant_id, l1.id, status="NEW", scheduled_at_utc=None, tz_name=tz_name
        )

        l2 = _create_lead(
            db,
            tenant_id,
            name="Samantha Lee",
            notes="Exterior trim + prep (unscheduled)",
            status="ACCEPTED",
        )
        _create_job(
            db, tenant_id, l2.id, status="NEW", scheduled_at_utc=None, tz_name=tz_name
        )

        # ---- Scheduled: Today 09:00 local
        dt_today_local = _make_local_dt(tz, days_from_today=0, hour=9, minute=0)
        dt_today_utc = dt_today_local.astimezone(timezone.utc)

        l3 = _create_lead(
            db,
            tenant_id,
            name="Jordan Smith",
            notes="Kitchen walls + ceiling (scheduled today)",
            status="ACCEPTED",
        )
        _create_job(
            db,
            tenant_id,
            l3.id,
            status="SCHEDULED",
            scheduled_at_utc=dt_today_utc,
            tz_name=tz_name,
        )

        # ---- Scheduled: Tomorrow 13:00 local
        dt_tom_local = _make_local_dt(tz, days_from_today=1, hour=13, minute=0)
        dt_tom_utc = dt_tom_local.astimezone(timezone.utc)

        l4 = _create_lead(
            db,
            tenant_id,
            name="Taylor Johnson",
            notes="Cabinet doors spray (scheduled tomorrow)",
            status="ACCEPTED",
        )
        _create_job(
            db,
            tenant_id,
            l4.id,
            status="SCHEDULED",
            scheduled_at_utc=dt_tom_utc,
            tz_name=tz_name,
        )

        db.commit()

        print("✅ Seed calendar demo done")
        print("TENANT_ID:", tenant_id)
        print("TZ:", tz_name)
        print("Created leads:", l1.id, l2.id, l3.id, l4.id)

    finally:
        db.close()


if __name__ == "__main__":
    main()
