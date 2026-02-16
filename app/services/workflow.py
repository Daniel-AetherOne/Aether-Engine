# app/services/workflow.py
from __future__ import annotations

from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.models.lead import Lead
from app.models.job import Job

JOB_TO_LEAD = {
    "DONE": "COMPLETED",
    "CANCELLED": "CANCELLED",
    # optioneel:
    # "IN_PROGRESS": "IN_PROGRESS",
    # "SCHEDULED": "SCHEDULED",
}


def ensure_job_for_lead(db: Session, lead: Lead) -> Job:
    job = db.query(Job).filter(Job.lead_id == lead.id).first()
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
        lead.sent_at = datetime.now(timezone.utc)
    db.add(lead)


def mark_lead_viewed(db: Session, lead: Lead) -> None:
    if hasattr(lead, "viewed_at") and getattr(lead, "viewed_at", None):
        return
    if hasattr(lead, "viewed_at"):
        lead.viewed_at = datetime.now(timezone.utc)
    if (lead.status or "").upper() == "SENT":
        lead.status = "VIEWED"
    db.add(lead)


def mark_lead_accepted(db: Session, lead: Lead) -> None:
    lead.status = "ACCEPTED"
    if hasattr(lead, "accepted_at") and not getattr(lead, "accepted_at", None):
        lead.accepted_at = datetime.now(timezone.utc)
    db.add(lead)
