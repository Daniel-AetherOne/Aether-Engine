# app/routers/router_app.py
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request, Form, Query
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, func
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
import logging

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

logger = logging.getLogger(__name__)


# -------------------------
# Time helpers
# -------------------------
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _safe_tz(tz_name: str | None) -> str:
    tz = (tz_name or "").strip()
    if not tz:
        return "America/New_York"
    try:
        ZoneInfo(tz)
        return tz
    except Exception:
        return "America/New_York"


def _get_tenant_timezone(current_user: User, job: Job | None = None) -> str:
    # 1) Keep display consistent if job already has a stored timezone
    if job is not None:
        existing = getattr(job, "scheduled_tz", None)
        if existing:
            return _safe_tz(str(existing))

    # 2) Tenant/user setting
    return _safe_tz(getattr(current_user, "timezone", None))


def _parse_datetime_local(value: str) -> datetime:
    # HTML <input type="datetime-local"> gives "YYYY-MM-DDTHH:MM"
    return datetime.strptime(value, "%Y-%m-%dT%H:%M")


def _local_naive_to_utc(dt_local_naive: datetime, tz_name: str) -> datetime:
    tz = ZoneInfo(tz_name)
    dt_local = dt_local_naive.replace(tzinfo=tz)
    return dt_local.astimezone(timezone.utc)


def _utc_to_local_input(dt_utc: datetime | None, tz_name: str) -> str:
    if not dt_utc:
        return ""
    tz = ZoneInfo(tz_name)
    return dt_utc.astimezone(tz).strftime("%Y-%m-%dT%H:%M")


def _utc_to_local_human(dt_utc: datetime | None, tz_name: str) -> str:
    if not dt_utc:
        return ""
    tz = ZoneInfo(tz_name)
    return dt_utc.astimezone(tz).strftime("%b %d, %Y %H:%M")


# -------------------------
# Dev helper (optional)
# -------------------------
@router.post("/dev/set_timezone")
def dev_set_timezone(
    tz: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user_html),
):
    tz = (tz or "").strip()
    try:
        ZoneInfo(tz)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid timezone")

    current_user.timezone = tz
    db.add(current_user)
    db.commit()
    return RedirectResponse(url="/app/dashboard", status_code=303)


# -------------------------
# Lead status helpers
# -------------------------
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


# -------------------------
# App routes
# -------------------------
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

    kpis = {s: job_counts.get(s, 0) for s in ALLOWED_JOB_STATUSES}

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

    # MVP: 1 query per lead OK. Later optimize with join.
    rows = []
    for lead in leads:
        job = (
            db.query(Job)
            .filter(
                Job.lead_id == lead.id, Job.tenant_id == str(current_user.tenant_id)
            )
            .first()
        )
        rows.append(
            {
                "id": lead.id,
                "customer_name": getattr(lead, "name", "") or "—",
                "address": "",
                "status": derive_status(lead),
                "estimate_html_key": getattr(lead, "estimate_html_key", None),
                "public_url": public_url_for(request, lead),
                "next_action": compute_next_action(lead, job),
                "total": getattr(lead, "total", None),
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

    job = (
        db.query(Job)
        .filter(Job.lead_id == lead.id, Job.tenant_id == str(current_user.tenant_id))
        .first()
    )

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

    tz_name = _get_tenant_timezone(current_user, job)

    scheduled_input_value = (
        _utc_to_local_input(getattr(job, "scheduled_at", None), tz_name) if job else ""
    )
    scheduled_display = (
        _utc_to_local_human(getattr(job, "scheduled_at", None), tz_name) if job else ""
    )

    started_display = (
        _utc_to_local_human(getattr(job, "started_at", None), tz_name) if job else ""
    )
    done_display = (
        _utc_to_local_human(getattr(job, "done_at", None), tz_name) if job else ""
    )

    return templates.TemplateResponse(
        "app/lead_detail.html",
        {
            "request": request,
            "lead": vm,
            "job": job,
            "tz_name": tz_name,
            "scheduled_input_value": scheduled_input_value,
            "scheduled_display": scheduled_display,
            "started_display": started_display,
            "done_display": done_display,
        },
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

    try:
        html = get_text(storage, tenant_id=str(current_user.tenant_id), key=html_key)
        return HTMLResponse(content=html)

    except RuntimeError as e:
        msg = str(e)

        # alleen "missing file" netjes afhandelen
        if "HeadObject" in msg and ("404" in msg or "Not Found" in msg):
            logger.warning(
                "estimate_html_missing tenant=%s key=%s",
                current_user.tenant_id,
                html_key,
            )
            return templates.TemplateResponse(
                "estimate_missing.html",
                {
                    "request": request,
                    "missing_key": html_key,
                    "lead_id": lead_id,
                    "tenant_id": str(current_user.tenant_id),
                },
                status_code=404,
            )

        # echte errors niet verbergen
        raise

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


# -------------------------
# Jobs
# -------------------------
def _get_job_or_404(db: Session, job_id: int, tenant_id: str) -> Job:
    job = db.query(Job).filter(Job.id == job_id, Job.tenant_id == tenant_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


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

    job = _get_job_or_404(db, job_id, tenant_id=str(current_user.tenant_id))

    job.status = s
    db.add(job)
    db.commit()

    return RedirectResponse(url=f"/app/leads/{job.lead_id}#job", status_code=303)


@router.get("/jobs", response_class=HTMLResponse)
def app_jobs_list(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user_html),
    status: str | None = Query(default=None),
):
    tenant_id = str(current_user.tenant_id)

    counts_rows = (
        db.query(Job.status, func.count(Job.id))
        .filter(Job.tenant_id == tenant_id)
        .group_by(Job.status)
        .all()
    )
    counts_map = {str(s): int(c) for s, c in counts_rows}
    counts = {s: counts_map.get(s, 0) for s in sorted(ALLOWED_JOB_STATUSES)}

    q = db.query(Job).filter(Job.tenant_id == tenant_id)

    status_norm = (status or "").upper().strip() if status else None
    if status_norm:
        if status_norm not in ALLOWED_JOB_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid status filter")
        q = q.filter(Job.status == status_norm)

    order_col = (
        getattr(Job, "updated_at", None) or getattr(Job, "created_at", None) or Job.id
    )
    jobs = q.order_by(desc(order_col)).limit(200).all()

    lead_ids = [j.lead_id for j in jobs]
    leads = db.query(Lead).filter(Lead.id.in_(lead_ids)).all() if lead_ids else []
    lead_map = {l.id: l for l in leads}

    tz_name = _get_tenant_timezone(current_user, None)

    tz = ZoneInfo(tz_name)
    today_local = datetime.now(tz).date()
    tomorrow_local = today_local + timedelta(days=1)

    rows = []
    for j in jobs:
        l = lead_map.get(j.lead_id)

        when_label = ""
        if getattr(j, "scheduled_at", None):
            d = j.scheduled_at.astimezone(tz).date()
            if d == today_local:
                when_label = "Today"
            elif d == tomorrow_local:
                when_label = "Tomorrow"

        rows.append(
            {
                "id": j.id,
                "status": (j.status or "").upper(),
                "lead_id": j.lead_id,
                "customer": (getattr(l, "name", "") or "—") if l else "—",
                "email": (getattr(l, "email", "") or "") if l else "",
                "scheduled_at": getattr(j, "scheduled_at", None),
                "scheduled_at_local": (
                    _utc_to_local_human(getattr(j, "scheduled_at", None), tz_name)
                    if getattr(j, "scheduled_at", None)
                    else ""
                ),
                "scheduled_tz": getattr(j, "scheduled_tz", None),
                "when_label": when_label,
                "updated_at": getattr(j, "updated_at", None),
            }
        )

    return templates.TemplateResponse(
        "app/jobs_list.html",
        {
            "request": request,
            "jobs": rows,
            "counts": counts,
            "active_status": status_norm,
        },
    )


@router.post("/jobs/{job_id}/schedule")
def job_schedule(
    job_id: int,
    scheduled_at_local: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user_html),
):
    job = _get_job_or_404(db, job_id, tenant_id=str(current_user.tenant_id))

    # guard: block closed jobs
    if (job.status or "").upper() in ("DONE", "CANCELLED"):
        raise HTTPException(status_code=400, detail="Cannot schedule a closed job")

    tz_name = _get_tenant_timezone(current_user, job)

    dt_local_naive = _parse_datetime_local(scheduled_at_local)
    dt_utc = _local_naive_to_utc(dt_local_naive, tz_name)

    job.scheduled_at = dt_utc

    # Store tz if field exists
    if hasattr(job, "scheduled_tz"):
        job.scheduled_tz = tz_name

    # Auto status
    if (job.status or "").upper() in ("NEW", "SCHEDULED"):
        job.status = "SCHEDULED"

    db.add(job)
    db.commit()
    return RedirectResponse(url=f"/app/leads/{job.lead_id}#job", status_code=303)


@router.post("/jobs/{job_id}/quick_schedule")
def job_quick_schedule(
    job_id: int,
    day_offset: int = Form(...),  # 0 = today, 1 = tomorrow, 2 = +2
    hhmm: str = Form(...),  # "09:00" / "13:00"
    return_to: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user_html),
):
    job = _get_job_or_404(db, job_id, tenant_id=str(current_user.tenant_id))

    if (job.status or "").upper() in ("DONE", "CANCELLED"):
        raise HTTPException(status_code=400, detail="Cannot schedule a closed job")

    tz_name = _get_tenant_timezone(current_user, job)
    tz = ZoneInfo(tz_name)

    # Build local datetime: (today + offset) at hh:mm, in tenant tz
    now_local = datetime.now(tz)
    base_date = now_local.date() + timedelta(days=int(day_offset))

    try:
        hh, mm = hhmm.split(":")
        hour = int(hh)
        minute = int(mm)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid time")

    dt_local = datetime(
        year=base_date.year,
        month=base_date.month,
        day=base_date.day,
        hour=hour,
        minute=minute,
        tzinfo=tz,
    )
    dt_utc = dt_local.astimezone(timezone.utc)

    job.scheduled_at = dt_utc
    if hasattr(job, "scheduled_tz"):
        job.scheduled_tz = tz_name

    if (job.status or "").upper() in ("NEW", "SCHEDULED"):
        job.status = "SCHEDULED"

    db.add(job)
    db.commit()

    # Redirect back to calendar by default
    dest = return_to or "/app/calendar"
    return RedirectResponse(url=dest, status_code=303)


@router.post("/jobs/{job_id}/unschedule")
def job_unschedule(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user_html),
):
    job = _get_job_or_404(db, job_id, tenant_id=str(current_user.tenant_id))

    if (job.status or "").upper() in ("DONE", "CANCELLED"):
        raise HTTPException(status_code=400, detail="Cannot unschedule a closed job")

    job.scheduled_at = None
    if hasattr(job, "scheduled_tz"):
        job.scheduled_tz = _get_tenant_timezone(current_user, job)

    if (job.status or "").upper() == "SCHEDULED":
        job.status = "NEW"

    db.add(job)
    db.commit()
    return RedirectResponse(url=f"/app/leads/{job.lead_id}#job", status_code=303)


@router.post("/jobs/{job_id}/schedule_now")
def job_schedule_now(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user_html),
):
    job = _get_job_or_404(db, job_id, tenant_id=str(current_user.tenant_id))

    now = _utcnow()
    if not getattr(job, "scheduled_at", None):
        job.scheduled_at = now

    if hasattr(job, "scheduled_tz") and not getattr(job, "scheduled_tz", None):
        job.scheduled_tz = _get_tenant_timezone(current_user, job)

    if (job.status or "").upper() == "NEW":
        job.status = "SCHEDULED"

    db.add(job)
    db.commit()
    return RedirectResponse(url=f"/app/leads/{job.lead_id}#job", status_code=303)


@router.post("/jobs/{job_id}/start")
def job_start(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user_html),
):
    job = _get_job_or_404(db, job_id, tenant_id=str(current_user.tenant_id))

    # Guardrail: require scheduling before starting
    if not getattr(job, "scheduled_at", None):
        raise HTTPException(status_code=400, detail="Schedule the job first")

    now = _utcnow()
    if not getattr(job, "started_at", None):
        job.started_at = now

    job.status = "IN_PROGRESS"

    db.add(job)
    db.commit()
    return RedirectResponse(url=f"/app/leads/{job.lead_id}#job", status_code=303)


@router.post("/jobs/{job_id}/done")
def job_done(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user_html),
):
    job = _get_job_or_404(db, job_id, tenant_id=str(current_user.tenant_id))

    now = _utcnow()
    if not getattr(job, "done_at", None):
        job.done_at = now

    job.status = "DONE"

    db.add(job)
    db.commit()
    return RedirectResponse(url=f"/app/leads/{job.lead_id}#job", status_code=303)


@router.get("/calendar", response_class=HTMLResponse)
def app_calendar_week(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user_html),
    week: str | None = Query(default=None),
    show_done: int = Query(default=0),
):
    tenant_id = str(current_user.tenant_id)
    tz_name = _get_tenant_timezone(current_user, None)
    tz = ZoneInfo(tz_name)

    now_local = datetime.now(tz)

    # -------- week start bepalen
    if week:
        try:
            year_str, w_str = week.split("-W")
            year = int(year_str)
            week_no = int(w_str)
            week_start_local = datetime.fromisocalendar(year, week_no, 1).replace(
                hour=0, minute=0, second=0, microsecond=0, tzinfo=tz
            )
        except Exception:
            week_start_local = (
                now_local - timedelta(days=now_local.weekday())
            ).replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        week_start_local = (now_local - timedelta(days=now_local.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    week_end_local = week_start_local + timedelta(days=7)

    week_start_utc = week_start_local.astimezone(timezone.utc)
    week_end_utc = week_end_local.astimezone(timezone.utc)

    # -------- status filter (toggle DONE)
    include_statuses = {"SCHEDULED", "IN_PROGRESS"}
    if show_done:
        include_statuses.add("DONE")

    # -------- scheduled jobs
    jobs = (
        db.query(Job)
        .filter(
            Job.tenant_id == tenant_id,
            Job.scheduled_at.isnot(None),
            Job.scheduled_at >= week_start_utc,
            Job.scheduled_at < week_end_utc,
            Job.status.in_(list(include_statuses)),
        )
        .order_by(Job.scheduled_at.asc())
        .all()
    )

    # -------- unscheduled NEW jobs (sidebar)
    unscheduled = (
        db.query(Job)
        .filter(
            Job.tenant_id == tenant_id,
            Job.scheduled_at.is_(None),
            Job.status == "NEW",
        )
        .order_by(desc(getattr(Job, "updated_at", Job.id)))
        .limit(50)
        .all()
    )

    # -------- leads ophalen
    lead_ids = [j.lead_id for j in jobs] + [u.lead_id for u in unscheduled]
    lead_ids = list({lid for lid in lead_ids if lid})
    leads = db.query(Lead).filter(Lead.id.in_(lead_ids)).all() if lead_ids else []
    lead_map = {l.id: l for l in leads}

    # -------- dagen bouwen
    days = []
    for i in range(7):
        dt = week_start_local + timedelta(days=i)
        days.append(
            {
                "date": dt.date().isoformat(),
                "title": dt.strftime("%a"),
                "is_today": dt.date() == now_local.date(),
                "items": [],
                "counts": {"TOTAL": 0, "SCHEDULED": 0, "IN_PROGRESS": 0, "DONE": 0},
            }
        )

    def day_index(dt_utc: datetime) -> int:
        dt_local = dt_utc.astimezone(tz)
        return (dt_local.date() - week_start_local.date()).days

    # -------- jobs per dag
    for j in jobs:
        idx = day_index(j.scheduled_at)
        if idx < 0 or idx > 6:
            continue

        lead = lead_map.get(j.lead_id)
        dt_local = j.scheduled_at.astimezone(tz)

        item = {
            "job_id": j.id,
            "lead_id": j.lead_id,
            "status": (j.status or "").upper(),
            "time": dt_local.strftime("%H:%M"),
            "customer": (getattr(lead, "name", "") or "—") if lead else "—",
            "notes": (getattr(lead, "notes", "") or "") if lead else "",
        }

        days[idx]["items"].append(item)

        st = item["status"]
        days[idx]["counts"]["TOTAL"] += 1
        if st in days[idx]["counts"]:
            days[idx]["counts"][st] += 1

    # sort times
    for d in days:
        d["items"].sort(key=lambda x: x["time"])

    # -------- unscheduled vm
    unscheduled_vm = []
    for u in unscheduled:
        lead = lead_map.get(u.lead_id)
        unscheduled_vm.append(
            {
                "job_id": u.id,
                "lead_id": u.lead_id,
                "customer": (getattr(lead, "name", "") or "—") if lead else "—",
                "notes": (getattr(lead, "notes", "") or "") if lead else "",
            }
        )

    # -------- nav
    iso = week_start_local.isocalendar()
    year, week_no, _ = iso

    prev_start = week_start_local - timedelta(days=7)
    next_start = week_start_local + timedelta(days=7)

    prev_iso = prev_start.isocalendar()
    next_iso = next_start.isocalendar()

    prev_week = f"{prev_iso.year}-W{prev_iso.week:02d}"
    next_week = f"{next_iso.year}-W{next_iso.week:02d}"

    week_label = (
        f"Week {week_no} · {week_start_local.date()} → "
        f"{(week_end_local - timedelta(days=1)).date()}"
    )

    now_chip = now_local.strftime("%a %b %d · %H:%M")

    toggle_done_url = (
        f"/app/calendar?week={year}-W{week_no:02d}&show_done={0 if show_done else 1}"
    )

    return templates.TemplateResponse(
        "app/calendar_week.html",
        {
            "request": request,
            "tz_name": tz_name,
            "week_label": week_label,
            "now_chip": now_chip,
            "days": days,
            "prev_week": prev_week,
            "next_week": next_week,
            "unscheduled": unscheduled_vm,
            "show_done": show_done,
            "toggle_done_url": toggle_done_url,
        },
    )
