# app/workflow/status.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.models.lead import Lead
from app.models.job import Job
from app.services.workflow import ensure_job_for_lead

LEAD_TERMINAL = {"ACCEPTED"}  # later ook DECLINED etc.
JOB_TERMINAL = {"DONE", "CANCELLED"}


@dataclass
class WorkflowResult:
    lead_changed: bool = False
    job_changed: bool = False
    created_job: bool = False


def sync_lead_from_job(lead: Lead, job: Optional[Job]) -> bool:
    """
    Optioneel: als job DONE => lead wordt COMPLETED (later).
    Voor Fase 9 houden we lead.status voor sales funnel: SENT/VIEWED/ACCEPTED.
    """
    return False


def sync_job_from_lead(lead: Lead, job: Optional[Job]) -> bool:
    """
    Regels:
    - lead ACCEPTED => job bestaat (minstens NEW), maar we overrulen status niet.
    """
    if not job:
        return False

    ls = (lead.status or "").upper()
    if ls == "ACCEPTED" and (job.status or "").upper() not in JOB_TERMINAL:
        return False

    return False


def apply_workflow(db: Session, lead: Lead) -> WorkflowResult:
    """
    Idempotent: meerdere keren aanroepen is veilig.
    """
    res = WorkflowResult()

    ls = (lead.status or "").upper()

    job: Job | None = None
    if ls == "ACCEPTED":
        # ✅ single source of truth (tenant-safe)
        before = (
            db.query(Job)
            .filter(Job.lead_id == lead.id, Job.tenant_id == str(lead.tenant_id))
            .first()
        )
        job = ensure_job_for_lead(db, lead)
        res.created_job = before is None

    # sync rules (nu nog no-ops)
    if job:
        if sync_job_from_lead(lead, job):
            res.job_changed = True
        if sync_lead_from_job(lead, job):
            res.lead_changed = True

    return res
