# app/workflow/status.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.lead import Lead
from app.models.job import Job

LEAD_TERMINAL = {"ACCEPTED"}  # later ook DECLINED etc.
JOB_TERMINAL = {"DONE", "CANCELLED"}


@dataclass
class WorkflowResult:
    lead_changed: bool = False
    job_changed: bool = False
    created_job: bool = False


def ensure_job(db: Session, lead: Lead) -> tuple[Job, bool]:
    job = db.query(Job).filter(Job.lead_id == lead.id).first()
    if job:
        return job, False

    job = Job(
        tenant_id=str(lead.tenant_id),
        lead_id=lead.id,
        status="NEW",
    )
    db.add(job)
    return job, True


def sync_lead_from_job(lead: Lead, job: Optional[Job]) -> bool:
    """
    Optioneel: als job DONE => lead blijft ACCEPTED (of wordt COMPLETED als je dat wil).
    Voor nu laten we lead.status vooral door 'SENT/VIEWED/ACCEPTED' lopen.
    """
    return False


def sync_job_from_lead(lead: Lead, job: Optional[Job]) -> bool:
    """
    Regels:
    - lead ACCEPTED => job minimaal NEW (als job nog niet terminal is)
    """
    if not job:
        return False

    ls = (lead.status or "").upper()
    if ls == "ACCEPTED" and (job.status or "").upper() not in JOB_TERMINAL:
        # job mag NEW blijven of later SCHEDULED etc.
        return False

    return False


def apply_workflow(db: Session, lead: Lead) -> WorkflowResult:
    """
    Idempotent: meerdere keren aanroepen is veilig.
    """
    res = WorkflowResult()

    ls = (lead.status or "").upper()

    job = None
    if ls == "ACCEPTED":
        job, created = ensure_job(db, lead)
        res.created_job = created

    # sync rules
    if job:
        if sync_job_from_lead(lead, job):
            res.job_changed = True
        if sync_lead_from_job(lead, job):
            res.lead_changed = True

    return res
