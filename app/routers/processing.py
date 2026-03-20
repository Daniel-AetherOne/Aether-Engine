from __future__ import annotations

import logging

from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
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
        # SUCCEEDED: route that is immediately available when estimate_html_key exists.
        # NEEDS_REVIEW: customer thank-you flow.
        redirect_url = f"/quotes/{lead_id}/html" if s == "SUCCEEDED" else "/thank-you"
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

    # Autostart: als de lead nog nooit is gestart (NEW), start dan de quote
    # zodat /processing/{lead_id} ook werkt als een oude redirect ooit nog
    # naar dit endpoint leidt.
    if (getattr(lead, "status", "") or "").upper() == "NEW":
        try:
            from app.routers.quotes import publish_quote

            publish_quote(
                lead_id=lead.id,
                background=BackgroundTasks(),
                db=db,
            )
            lead = db.query(Lead).filter(Lead.id == lead_id).first()
        except Exception as e:
            lead.status = "FAILED"
            lead.error_message = str(e)
            lead.updated_at = datetime.now(timezone.utc)
            db.add(lead)
            db.commit()
            db.refresh(lead)

    # 1) Lead niet bestaat: handled hierboven.
    # 2) Verwerking gefaald: lead.status == FAILED (of error_message aanwezig).
    lead_status = (getattr(lead, "status", "") or "").upper()
    error_message = (getattr(lead, "error_message", None) or None)

    if lead_status == "FAILED" or error_message:
        response = {
            "lead_id": str(lead.id),
            "status": "failed",
            "redirect_url": None,
            "error": error_message or "Onbekende fout",
        }
        logger.info(
            "PROCESSING_STATUS_RESPONSE lead_id=%s status=%s redirect_url=%s route=%s",
            response["lead_id"],
            response["status"],
            response["redirect_url"],
            "/processing/{lead_id}",
        )
        return response

    # 3) Done/final redirect decisions (single processing page flow).
    mapped_status, redirect_url, _ = _map_lead_status_for_ui(
        lead_status=lead_status, lead_id=str(lead.id)
    )
    has_estimate_html = bool((getattr(lead, "estimate_html_key", None) or "").strip())
    is_done_available = (
        (lead_status == "SUCCEEDED" and has_estimate_html)
        or (lead_status == "NEEDS_REVIEW")
    )
    if mapped_status == "done" and is_done_available:
        response = {
            "lead_id": str(lead.id),
            "status": "done",
            "redirect_url": redirect_url,
            "error": None,
        }
        logger.info(
            "PROCESSING_STATUS_RESPONSE lead_id=%s status=%s redirect_url=%s route=%s",
            response["lead_id"],
            response["status"],
            response["redirect_url"],
            "/quotes/{lead_id}/html"
            if str(redirect_url).startswith("/quotes/")
            else "/thank-you",
        )
        return response

    # 4) Anders => running.
    #    Watchdog: als de backend blijft hangen op RUNNING, ontgrendelen we de UX.
    if lead_status == "RUNNING":
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

                response = {
                    "lead_id": str(lead.id),
                    "status": "failed",
                    "redirect_url": None,
                    "error": lead.error_message or "Onbekende fout",
                }
                logger.info(
                    "PROCESSING_STATUS_RESPONSE lead_id=%s status=%s redirect_url=%s route=%s",
                    response["lead_id"],
                    response["status"],
                    response["redirect_url"],
                    "/processing/{lead_id}",
                )
                return response

    response = {
        "lead_id": str(lead.id),
        "status": "running",
        "redirect_url": None,
        "error": None,
    }
    logger.info(
        "PROCESSING_STATUS_RESPONSE lead_id=%s status=%s redirect_url=%s route=%s",
        response["lead_id"],
        response["status"],
        response["redirect_url"],
        "/processing/{lead_id}",
    )
    return response


@router.get("/processing/{lead_id}", response_class=HTMLResponse)
def processing_page(request: Request, lead_id: str, db: Session = Depends(get_db)) -> HTMLResponse:
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    # UX polish: if this route is hit again after completion, skip rendering
    # processing.html and redirect immediately to final route to avoid flash.
    lead_status = (getattr(lead, "status", "") or "").upper()
    mapped_status, redirect_url, _ = _map_lead_status_for_ui(
        lead_status=lead_status, lead_id=str(lead.id)
    )
    has_estimate_html = bool((getattr(lead, "estimate_html_key", None) or "").strip())
    is_done_available = (
        (lead_status == "SUCCEEDED" and has_estimate_html)
        or (lead_status == "NEEDS_REVIEW")
    )
    if mapped_status == "done" and is_done_available and redirect_url:
        logger.info(
            "PROCESSING_ROUTE_EARLY_REDIRECT lead_id=%s status=%s redirect_url=%s",
            str(lead.id),
            lead_status,
            redirect_url,
        )
        return RedirectResponse(url=str(redirect_url), status_code=303)

    logger.info(
        "PROCESSING_TEMPLATE_RENDER lead_id=%s template=%s",
        str(lead.id),
        "processing.html",
    )
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

