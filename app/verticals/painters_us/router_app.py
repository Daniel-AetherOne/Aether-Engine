from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from app.services.storage import get_storage, get_text
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.models.user import User
from datetime import datetime, timezone
import secrets
from fastapi.responses import JSONResponse
from app.models.job import Job

from app.auth.deps import require_user_html

from app.db import get_db
from app.models.lead import Lead

router = APIRouter(
    prefix="/app",
    tags=["painters_us_app"],
    dependencies=[Depends(require_user_html)],
)
templates = Jinja2Templates(directory="app/verticals/painters_us/templates")


def derive_status(lead: Lead) -> str:
    s = (getattr(lead, "status", "") or "").upper()
    if s in {"SENT", "VIEWED", "ACCEPTED"}:
        return s

    if getattr(lead, "needs_review_hard", False):
        return "NEEDS_REVIEW"
    if getattr(lead, "pricing_ready", False):
        return "SUCCEEDED"
    return "RUNNING"


@router.get("", include_in_schema=False)
def app_root():
    return RedirectResponse(url="/app/leads", status_code=302)


@router.get("/leads", response_class=HTMLResponse)
def app_leads(request: Request, db: Session = Depends(get_db)):

    leads = db.query(Lead).order_by(desc(Lead.created_at)).limit(100).all()

    rows = []
    for lead in leads:
        rows.append(
            {
                "id": str(lead.id),
                "customer_name": getattr(lead, "name", "") or "",
                "address": "",  # later uit intake_payload halen
                "email": getattr(lead, "email", "") or "",
                "status": derive_status(lead),
                "estimate_html_key": getattr(lead, "estimate_html_key", None),
                "total": getattr(lead, "total", None),
            }
        )

    return templates.TemplateResponse(
        "app/leads_list.html",
        {
            "request": request,
            "leads": rows,
        },
    )


@router.get("/leads/{lead_id}/estimate", response_class=HTMLResponse)
def app_lead_estimate(
    lead_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user_html),  # <-- dit geeft je tenant_id
):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    html_key = getattr(lead, "estimate_html_key", None)
    if not html_key:
        raise HTTPException(status_code=404, detail="Estimate HTML not found")

    storage = get_storage()

    # 1) Probeer tenant-prefixed (meest waarschijnlijk)
    try:
        html = get_text(storage, tenant_id=str(current_user.tenant_id), key=html_key)
        return HTMLResponse(content=html)
    except RuntimeError as e:
        # 2) Fallback: tenant-loos (oude data / lokaal)
        if "404" in str(e) or "Not Found" in str(e) or "not_found" in str(e):
            try:
                html = get_text(storage, tenant_id="", key=html_key)
                return HTMLResponse(content=html)
            except Exception:
                pass
        raise HTTPException(
            status_code=404,
            detail=f"Estimate HTML not found in storage for key={html_key}",
        )


@router.post("/leads/{lead_id}/send")
def send_estimate(
    lead_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user_html),
):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    if str(lead.tenant_id) != str(current_user.tenant_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    if not lead.estimate_html_key:
        raise HTTPException(status_code=400, detail="No estimate to send")

    if not lead.public_token:
        # 32 hex chars
        lead.public_token = secrets.token_hex(16)

    lead.status = "SENT"
    lead.sent_at = datetime.now(timezone.utc)

    db.add(lead)
    db.commit()

    public_url = f"{request.base_url}e/{lead.public_token}"
    return RedirectResponse(url=f"/app/leads/{lead_id}?sent=1", status_code=303)


@router.get("/leads/{lead_id}", response_class=HTMLResponse)
def app_lead_detail(request: Request, lead_id: str, db: Session = Depends(get_db)):

    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    job = db.query(Job).filter(Job.lead_id == lead.id).first()

    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    vm = {
        "id": str(lead.id),
        "status": derive_status(lead),
        "customer_name": getattr(lead, "customer_name", "") or "",
        "address": "",  # later uit intake_payload
        "project_description": getattr(lead, "notes", "") or "",
        "email": getattr(lead, "email", "") or "",
        "email": getattr(lead, "email", "") or "",
        "phone": getattr(lead, "phone", "") or "",
        "job_id": getattr(job, "id", None),
        "job_status": getattr(job, "status", None),
        "estimate_html_key": getattr(lead, "estimate_html_key", None),
        "needs_review_reasons": getattr(lead, "needs_review_reasons", None),
        "public_token": getattr(lead, "public_token", None),
    }

    return templates.TemplateResponse(
        "app/lead_detail.html",
        {
            "request": request,
            "lead": vm,
        },
    )
