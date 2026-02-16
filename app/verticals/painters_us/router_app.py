from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from datetime import datetime, timezone
import secrets
from fastapi import Query

from app.auth.deps import require_user_html
from app.db import get_db
from app.models.lead import Lead
from app.models.job import Job
from app.models.user import User
from app.services.storage import get_storage, get_text

router = APIRouter(
    prefix="/app",
    tags=["painters_us_app"],
    dependencies=[Depends(require_user_html)],
)
templates = Jinja2Templates(directory="app/verticals/painters_us/templates")


ALLOWED_JOB_STATUSES = {"NEW", "SCHEDULED", "IN_PROGRESS", "DONE", "CANCELLED"}


def _utcnow():
    return datetime.now(timezone.utc)


def derive_status(lead: Lead) -> str:
    s = (getattr(lead, "status", "") or "").upper()
    if s in {"SENT", "VIEWED", "ACCEPTED"}:
        return s

    if getattr(lead, "needs_review_hard", False):
        return "NEEDS_REVIEW"
    if getattr(lead, "pricing_ready", False):
        return "SUCCEEDED"
    return "RUNNING"


def public_url_for(request: Request, lead: Lead) -> str | None:
    token = getattr(lead, "public_token", None)
    if not token:
        return None
    return f"{request.base_url}e/{token}"


def compute_next_action(lead: Lead, job: Job | None) -> dict:
    lead_status = derive_status(lead)
    has_estimate = bool(getattr(lead, "estimate_html_key", None))
    has_public = bool(getattr(lead, "public_token", None))

    if not has_estimate:
        return {"label": "Open lead", "href": f"/app/leads/{lead.id}"}

    if lead_status not in {"SENT", "VIEWED", "ACCEPTED"}:
        return {
            "label": "Send estimate",
            "href": f"/app/leads/{lead.id}/send",
            "method": "POST",
        }

    if lead_status == "SENT":
        return (
            {"label": "Open public link", "href": f"/e/{lead.public_token}"}
            if has_public
            else {"label": "Open lead", "href": f"/app/leads/{lead.id}"}
        )

    if lead_status == "VIEWED":
        return (
            {"label": "Follow up (open)", "href": f"/e/{lead.public_token}"}
            if has_public
            else {"label": "Open lead", "href": f"/app/leads/{lead.id}"}
        )

    if lead_status == "ACCEPTED":
        if not job:
            return {"label": "View lead", "href": f"/app/leads/{lead.id}"}
        js = (job.status or "").upper()
        if js in {"NEW", "SCHEDULED", "IN_PROGRESS"}:
            return {"label": "Update job", "href": f"/app/leads/{lead.id}#job"}
        return {"label": "View lead", "href": f"/app/leads/{lead.id}"}

    return {"label": "Open lead", "href": f"/app/leads/{lead.id}"}


@router.get("", include_in_schema=False)
def app_root():
    return RedirectResponse(url="/app/dashboard", status_code=302)


@router.get("/dashboard", response_class=HTMLResponse)
def app_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user_html),
):
    job_counts = dict(
        db.query(Job.status, func.count(Job.id))
        .filter(Job.tenant_id == str(current_user.tenant_id))
        .group_by(Job.status)
        .all()
    )

    kpis = {
        "NEW": job_counts.get("NEW", 0),
        "SCHEDULED": job_counts.get("SCHEDULED", 0),
        "IN_PROGRESS": job_counts.get("IN_PROGRESS", 0),
        "DONE": job_counts.get("DONE", 0),
        "CANCELLED": job_counts.get("CANCELLED", 0),
    }

    jobs = (
        db.query(Job)
        .filter(Job.tenant_id == str(current_user.tenant_id))
        .order_by(desc(getattr(Job, "updated_at", Job.id)))
        .limit(25)
        .all()
    )

    leads = (
        db.query(Lead)
        .filter(Lead.tenant_id == str(current_user.tenant_id))
        .order_by(desc(Lead.created_at))
        .limit(25)
        .all()
    )

    jobs_vm = [{"id": j.id, "status": j.status, "lead_id": j.lead_id} for j in jobs]
    leads_vm = [
        {"id": l.id, "name": getattr(l, "name", ""), "status": derive_status(l)}
        for l in leads
    ]

    return templates.TemplateResponse(
        "app/dashboard.html",
        {"request": request, "kpis": kpis, "jobs": jobs_vm, "leads": leads_vm},
    )


@router.get("/leads", response_class=HTMLResponse)
def app_leads(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user_html),
):
    leads = (
        db.query(Lead)
        .filter(Lead.tenant_id == str(current_user.tenant_id))
        .order_by(desc(Lead.created_at))
        .limit(100)
        .all()
    )

    # MVP: 1 query per lead is OK. Later optimaliseren met join.
    rows = []
    for lead in leads:
        job = db.query(Job).filter(Job.lead_id == lead.id).first()
        rows.append(
            {
                "id": lead.id,
                "customer_name": getattr(lead, "name", "") or "—",
                "address": "",
                "status": derive_status(lead),
                "estimate_html_key": getattr(lead, "estimate_html_key", None),
                "public_url": public_url_for(request, lead),
                "next_action": compute_next_action(lead, job),
                "total": getattr(lead, "total", None),  # voorkomt jinja errors
            }
        )

    return templates.TemplateResponse(
        "app/leads_list.html",
        {"request": request, "leads": rows},
    )


@router.get("/leads/{lead_id}", response_class=HTMLResponse)
def app_lead_detail(
    request: Request,
    lead_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user_html),
):
    lead = (
        db.query(Lead)
        .filter(Lead.id == lead_id, Lead.tenant_id == str(current_user.tenant_id))
        .first()
    )
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    job = db.query(Job).filter(Job.lead_id == lead.id).first()

    vm = {
        "id": lead.id,
        "status": derive_status(lead),
        "customer_name": getattr(lead, "name", "") or "",
        "address": "",
        "project_description": getattr(lead, "notes", "") or "",
        "email": getattr(lead, "email", "") or "",
        "phone": getattr(lead, "phone", "") or "",
        "estimate_html_key": getattr(lead, "estimate_html_key", None),
        "needs_review_reasons": getattr(lead, "needs_review_reasons", None),
        "public_token": getattr(lead, "public_token", None),
    }

    return templates.TemplateResponse(
        "app/lead_detail.html",
        {"request": request, "lead": vm, "job": job},
    )


@router.get("/leads/{lead_id}/estimate", response_class=HTMLResponse)
def app_lead_estimate(
    lead_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user_html),
):
    lead = (
        db.query(Lead)
        .filter(Lead.id == lead_id, Lead.tenant_id == str(current_user.tenant_id))
        .first()
    )
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    html_key = getattr(lead, "estimate_html_key", None)
    if not html_key:
        raise HTTPException(status_code=404, detail="Estimate HTML not found")

    storage = get_storage()
    html = get_text(storage, tenant_id=str(current_user.tenant_id), key=html_key)
    return HTMLResponse(content=html)


@router.post("/leads/{lead_id}/send")
def send_estimate(
    lead_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user_html),
):
    lead = (
        db.query(Lead)
        .filter(Lead.id == lead_id, Lead.tenant_id == str(current_user.tenant_id))
        .first()
    )
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    if not lead.estimate_html_key:
        raise HTTPException(status_code=400, detail="No estimate to send")

    if not lead.public_token:
        lead.public_token = secrets.token_hex(16)

    lead.status = "SENT"
    lead.sent_at = _utcnow()
    db.add(lead)
    db.commit()

    return RedirectResponse(url=f"/app/leads/{lead_id}?sent=1", status_code=303)


@router.post("/jobs/{job_id}/status")
def app_job_set_status(
    request: Request,
    job_id: int,
    status: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user_html),
):
    s = (status or "").upper().strip()
    if s not in ALLOWED_JOB_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")

    job = (
        db.query(Job)
        .filter(Job.id == job_id, Job.tenant_id == str(current_user.tenant_id))
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job.status = s
    db.add(job)
    db.commit()

    return RedirectResponse(url=f"/app/leads/{job.lead_id}#job", status_code=303)


@router.get("/jobs", response_class=HTMLResponse)
def app_jobs_list(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user_html),
    status: str | None = Query(default=None),  # /app/jobs?status=NEW
):
    tenant_id = str(current_user.tenant_id)

    # counts per status (tenant scoped)
    counts_rows = (
        db.query(Job.status, func.count(Job.id))
        .filter(Job.tenant_id == tenant_id)
        .group_by(Job.status)
        .all()
    )
    counts_map = {str(s): int(c) for s, c in counts_rows}
    counts = {s: counts_map.get(s, 0) for s in sorted(ALLOWED_JOB_STATUSES)}

    # filter
    q = db.query(Job).filter(Job.tenant_id == tenant_id)

    status_norm = (status or "").upper().strip() if status else None
    if status_norm:
        if status_norm not in ALLOWED_JOB_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid status filter")
        q = q.filter(Job.status == status_norm)

    # order: most recent updates first, fallback created_at/id
    # (werkt ook als updated_at nog niet bestaat in sommige sqlite snapshots)
    order_col = (
        getattr(Job, "updated_at", None) or getattr(Job, "created_at", None) or Job.id
    )
    jobs = q.order_by(desc(order_col)).limit(200).all()

    # load related leads (1 extra query)
    lead_ids = [j.lead_id for j in jobs]
    leads = db.query(Lead).filter(Lead.id.in_(lead_ids)).all() if lead_ids else []
    lead_map = {l.id: l for l in leads}

    rows = []
    for j in jobs:
        l = lead_map.get(j.lead_id)
        rows.append(
            {
                "id": j.id,
                "status": (j.status or "").upper(),
                "lead_id": j.lead_id,
                "customer": (getattr(l, "name", "") or "—") if l else "—",
                "email": (getattr(l, "email", "") or "") if l else "",
                "scheduled_at": getattr(j, "scheduled_at", None),
                "updated_at": getattr(j, "updated_at", None),
            }
        )

    return templates.TemplateResponse(
        "app/jobs_list.html",
        {
            "request": request,
            "jobs": rows,
            "counts": counts,
            "active_status": status_norm,  # None of "NEW" etc.
        },
    )
