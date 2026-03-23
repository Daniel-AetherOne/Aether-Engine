# app/services/workflow.py
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session

from app.models.lead import Lead
from app.models.job import Job

JOB_TO_LEAD = {
    "DONE": "COMPLETED",
    "CANCELLED": "CANCELLED",
}


def _utcnow():
    return datetime.now(timezone.utc)


def _default_acceptance_schedule_window() -> tuple[datetime, datetime]:
    tz = ZoneInfo("Europe/Amsterdam")
    now_local = datetime.now(tz)
    next_day = now_local.date() + timedelta(days=1)
    start_local = datetime.combine(next_day, time(hour=9, minute=0), tzinfo=tz)
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = start_utc + timedelta(hours=4)
    return start_utc, end_utc


def ensure_job_for_lead(db: Session, lead: Lead) -> Job:
    # ✅ tenant-safe + idempotent
    job = (
        db.query(Job)
        .filter(Job.lead_id == lead.id, Job.tenant_id == str(lead.tenant_id))
        .first()
    )
    if job:
        return job

    job = Job(
        tenant_id=str(lead.tenant_id),
        lead_id=lead.id,
        status="NEW",
    )
    db.add(job)
    return job


def apply_job_to_lead_status(db: Session, lead: Lead, job: Job) -> None:
    new_lead_status = JOB_TO_LEAD.get((job.status or "").upper())
    if not new_lead_status:
        return
    if (lead.status or "").upper() != new_lead_status:
        lead.status = new_lead_status
        db.add(lead)


def mark_lead_sent(db: Session, lead: Lead) -> None:
    lead.status = "SENT"
    if hasattr(lead, "sent_at") and not getattr(lead, "sent_at", None):
        lead.sent_at = _utcnow()
    db.add(lead)


def mark_lead_viewed(db: Session, lead: Lead) -> None:
    # ✅ only first view sets viewed_at
    if hasattr(lead, "viewed_at") and getattr(lead, "viewed_at", None):
        return

    if hasattr(lead, "viewed_at"):
        lead.viewed_at = _utcnow()

    # ✅ only SENT -> VIEWED (no downgrades)
    if (lead.status or "").upper() == "SENT":
        lead.status = "VIEWED"

    db.add(lead)


def mark_lead_accepted(db: Session, lead: Lead) -> None:
    # ✅ idempotent accepted_at
    lead.status = "ACCEPTED"
    if hasattr(lead, "accepted_at") and not getattr(lead, "accepted_at", None):
        lead.accepted_at = _utcnow()
    has_start = bool(getattr(lead, "scheduled_start", None))
    has_end = bool(getattr(lead, "scheduled_end", None))
    if (not has_start) and (not has_end):
        start_utc, end_utc = _default_acceptance_schedule_window()
        lead.scheduled_start = start_utc
        lead.scheduled_end = end_utc
    db.add(lead)
