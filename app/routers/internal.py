# app/routers/internal.py
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Lead
from app.services.metrics import inc, snapshot  # ✅ only once

router = APIRouter(prefix="/internal", tags=["internal"])
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger(__name__)


def _load_lead(db: Session, lead_id: int) -> Lead:
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


# -------------------------
# Metrics (FASE 6)
# -------------------------
@router.get("/metrics")
def internal_metrics():
    return snapshot()


# -------------------------
# Leads UI
# -------------------------
@router.get("/leads", response_class=HTMLResponse)
def internal_leads(
    request: Request,
    status: str = "NEEDS_REVIEW",
    q: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    MVP internal list:
    /internal/leads?status=NEEDS_REVIEW
    Optional: q= search by email/name
    """
    qs = db.query(Lead)

    if status:
        qs = qs.filter(Lead.status == status)

    if q:
        like = f"%{q.strip()}%"
        qs = qs.filter((Lead.email.ilike(like)) | (Lead.name.ilike(like)))

    leads = (
        qs.order_by(Lead.updated_at.desc().nullslast(), Lead.id.desc()).limit(200).all()
    )

    return templates.TemplateResponse(
        "internal_leads.html",
        {"request": request, "leads": leads, "status": status, "q": q or ""},
    )


@router.get("/leads/{lead_id}", response_class=HTMLResponse)
def internal_lead_detail(request: Request, lead_id: int, db: Session = Depends(get_db)):
    lead = _load_lead(db, lead_id)
    return templates.TemplateResponse(
        "internal_lead_detail.html",
        {"request": request, "lead": lead},
    )


# -------------------------
# Admin actions (FASE 6)
# -------------------------
@router.post("/leads/{lead_id}/approve")
def internal_approve(lead_id: int, db: Session = Depends(get_db)):
    lead = _load_lead(db, lead_id)

    # MVP: only allow approve from NEEDS_REVIEW
    if lead.status != "NEEDS_REVIEW":
        raise HTTPException(
            status_code=409, detail=f"Lead status is {lead.status}, not NEEDS_REVIEW"
        )

    lead.status = "SUCCEEDED"
    lead.error_message = None
    lead.updated_at = datetime.utcnow()
    db.commit()

    inc("internal_approve_total")
    logger.info("LEAD %s internal_approve -> SUCCEEDED", lead.id)

    return RedirectResponse(url=f"/internal/leads/{lead_id}", status_code=303)


@router.post("/leads/{lead_id}/fail")
def internal_fail(
    lead_id: int,
    reason: str = "Manual review required",
    db: Session = Depends(get_db),
):
    lead = _load_lead(db, lead_id)

    lead.status = "FAILED"
    lead.error_message = reason
    lead.updated_at = datetime.utcnow()
    db.commit()

    inc("internal_fail_total")
    logger.info("LEAD %s internal_fail -> FAILED reason=%s", lead.id, reason)

    return RedirectResponse(url=f"/internal/leads/{lead_id}", status_code=303)


@router.post("/leads/{lead_id}/recompute")
def internal_recompute(lead_id: int, db: Session = Depends(get_db)):
    """
    Reset lead to NEW and clear artifacts so publish can recompute cleanly.
    Redirect to customer status page with autostart=1.
    """
    lead = _load_lead(db, lead_id)

    # Reset state
    lead.status = "NEW"
    lead.error_message = None
    if hasattr(lead, "estimate_json"):
        lead.estimate_json = None
    if hasattr(lead, "estimate_html_key"):
        lead.estimate_html_key = None

    lead.updated_at = datetime.utcnow()
    db.commit()

    inc("internal_recompute_total")
    logger.info("LEAD %s internal_recompute -> NEW", lead.id)

    # Kick publish from status page
    return RedirectResponse(
        url=f"/quotes/{lead_id}/status?autostart=1", status_code=303
    )
