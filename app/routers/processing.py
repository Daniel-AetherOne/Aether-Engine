from __future__ import annotations

import logging

from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Lead

logger = logging.getLogger(__name__)

router = APIRouter(tags=["processing"])


def _map_lead_status_for_ui(*, lead_status: str, lead_id: str) -> tuple[str, str | None, str | None]:
    """
    UI status flow:
    queued -> running -> done -> failed
    """
    s = (lead_status or "").upper()
    if s == "NEW":
        return "queued", None, None
    if s == "RUNNING":
        return "running", None, None
    if s in {"SUCCEEDED", "NEEDS_REVIEW"}:
        # Geen openbare "offerte" nodig bij review; we tonen dan een simpele bedank-pagina.
        redirect_url = f"/offerte/{lead_id}" if s == "SUCCEEDED" else "/thank-you"
        return "done", redirect_url, None
    if s == "FAILED":
        return "failed", None, None
    # Fallback: als er onbekende statuses bestaan, behandelen we die als "running".
    return "running", None, None


@router.get("/leads/{lead_id}/status")
def lead_status_json(lead_id: str, db: Session = Depends(get_db)) -> dict:
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    # Watchdog: als de backend blijft hangen op RUNNING (compute_quote hangt/blijft lang),
    # dan ontgrendelen we de UX door na een bepaalde tijd naar FAILED te schakelen.
    # (Minimale fix zodat gebruikers niet eeuwig in "running" blijven.)
    if (getattr(lead, "status", "") or "").upper() == "RUNNING":
        updated_at = getattr(lead, "updated_at", None)
        if isinstance(updated_at, datetime):
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=timezone.utc)
            age = datetime.now(timezone.utc) - updated_at
            if age > timedelta(minutes=15):
                lead.status = "FAILED"
                lead.error_message = (
                    "We konden je aanvraag niet op tijd verwerken. Probeer het later opnieuw."
                )
                lead.updated_at = datetime.now(timezone.utc)
                db.add(lead)
                db.commit()
                db.refresh(lead)

    status, redirect_url, _ = _map_lead_status_for_ui(
        lead_status=getattr(lead, "status", "") or "",
        lead_id=str(lead.id),
    )

    error = (getattr(lead, "error_message", None) or None) if status == "failed" else None

    return {
        "lead_id": str(lead.id),
        "status": status,
        "redirect_url": redirect_url,
        "error": error,
    }


@router.get("/processing/{lead_id}", response_class=HTMLResponse)
def processing_page(request: Request, lead_id: str, db: Session = Depends(get_db)) -> HTMLResponse:
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    return request.app.state.templates.TemplateResponse(
        "processing.html",
        {
            "request": request,
            "lead_id": str(lead.id),
        },
    )


@router.get("/offerte/{lead_id}")
def offerte_redirect(lead_id: str, db: Session = Depends(get_db)):
    """
    Customer-friendly offerte URL.
    Verwijst naar de bestaande publieke /e/{public_token} pagina.
    """
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    if not getattr(lead, "public_token", None):
        raise HTTPException(status_code=404, detail="Offerte nog niet beschikbaar")

    return RedirectResponse(url=f"/e/{lead.public_token}", status_code=303)


@router.get("/thank-you", response_class=HTMLResponse)
def thank_you_page(request: Request, lead_id: str | None = None) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(
        "thank_you.html",
        {
            "request": request,
            "lead_id": lead_id,
        },
    )

