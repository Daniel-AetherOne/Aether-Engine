# app/routers/quotes.py
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.db import get_db
from app.models import Lead, LeadFile
from app.services.storage import get_storage, head_ok, MAX_BYTES, ALLOWED_CONTENT_TYPES
from app.services.metrics import inc  # ✅ FASE 6 metrics
from app.verticals.registry import get as get_vertical

router = APIRouter(prefix="/quotes", tags=["quotes"])
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger(__name__)


def _load_lead(db: Session, lead_id: int) -> Lead:
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


def _normalize_compute_result(result: Any) -> Tuple[Dict[str, Any], str, bool]:
    """
    Supports:
    - dict: {"estimate_json": <dict|jsonstr>, "estimate_html_key": str, "needs_review": bool}
    - legacy tuple: (estimate_dict, html, needs_review, html_key)
    """
    if isinstance(result, dict):
        est = result.get("estimate_json")
        if isinstance(est, str):
            try:
                estimate_dict = json.loads(est)
            except Exception:
                estimate_dict = {"raw": est}
        else:
            estimate_dict = est or {}

        html_key = str(result.get("estimate_html_key") or "")
        needs_review = bool(result.get("needs_review", False))
        return estimate_dict, html_key, needs_review

    if isinstance(result, (tuple, list)) and len(result) == 4:
        estimate_dict, _html, needs_review, html_key = result
        if not isinstance(estimate_dict, dict):
            estimate_dict = {"raw": estimate_dict}
        return estimate_dict, str(html_key or ""), bool(needs_review)

    raise RuntimeError("compute_quote returned unsupported result")


def _strip_tenant_prefix(tenant_id: str, key: str) -> str:
    key = (key or "").strip()
    if not key:
        return ""
    prefix = f"{tenant_id}/"
    return key[len(prefix) :] if key.startswith(prefix) else key


def _preflight_uploads_or_fail(lead: Lead, files: list[LeadFile]) -> None:
    """
    FASE 3:
    - max files
    - alle keys bestaan echt in storage (HEAD)
    - size <= MAX_BYTES
    - content-type allowed
    """
    if len(files) > settings.UPLOAD_MAX_FILES:
        raise RuntimeError(f"Too many files attached (max {settings.UPLOAD_MAX_FILES})")

    storage = get_storage()
    tenant_id = (lead.tenant_id or "").strip() or "default"

    for f in files:
        raw_key = (getattr(f, "s3_key", None) or "").strip()
        if not raw_key:
            raise RuntimeError("File record missing s3_key")

        # backward compat: als er nog tenant-prefixed keys in DB zitten, strippen
        key = _strip_tenant_prefix(tenant_id, raw_key)

        ok, meta, err = head_ok(storage, tenant_id, key)
        if not ok:
            # err is bv: wrong_prefix/head_not_found/size_exceeded/bad_content_type
            raise RuntimeError(f"Upload invalid: {raw_key} ({err})")

        # extra message met echte values (handig)
        if meta:
            size = int(meta.get("ContentLength", 0) or 0)
            ctype = str(meta.get("ContentType", "") or "").split(";")[0].strip()

            if size <= 0:
                raise RuntimeError(f"Empty upload: {raw_key}")
            if size > MAX_BYTES:
                raise RuntimeError(
                    f"Upload too large: {raw_key} (max {MAX_BYTES} bytes)"
                )
            if ALLOWED_CONTENT_TYPES and ctype and ctype not in ALLOWED_CONTENT_TYPES:
                raise RuntimeError(f"Unsupported upload type: {ctype} ({raw_key})")


def _set_failed(db: Session, lead: Lead, msg: str, http_status: int = 400):
    """
    Central failure path:
    - sets lead FAILED + error_message
    - increments metrics
    - raises HTTPException
    """
    lead.status = "FAILED"
    lead.error_message = msg
    lead.updated_at = datetime.utcnow()
    db.commit()

    inc("quotes_failed_total")
    logger.warning("LEAD %s FAILED reason=%s", lead.id, msg)

    raise HTTPException(status_code=http_status, detail=msg)


# =========================
# FASE 2 — UX endpoints
# =========================
@router.get("/{lead_id}/status", response_class=HTMLResponse)
def quote_status_page(request: Request, lead_id: int, db: Session = Depends(get_db)):
    lead = _load_lead(db, lead_id)
    autostart = int(request.query_params.get("autostart", "1"))

    logger.info(
        "STATUS_PAGE autostart=%s lead=%s status=%s",
        autostart,
        lead.id,
        lead.status,
    )

    return templates.TemplateResponse(
        "quote_status.html",
        {
            "request": request,
            "lead_id": lead.id,
            "lead": lead,
            "autostart": autostart,
        },
    )


@router.get("/{lead_id}/status.json")
def quote_status_json(lead_id: int, db: Session = Depends(get_db)):
    lead = _load_lead(db, lead_id)

    # ✅ server-side autostart: als NEW, start publish
    if lead.status == "NEW":
        logger.info("STATUS_JSON autostart publish lead=%s", lead.id)
        try:
            publish_quote(lead_id=lead.id, db=db)
            # publish_quote commits; reload fresh state for response
            lead = _load_lead(db, lead_id)
        except Exception as e:
            logger.exception("STATUS_JSON publish failed lead=%s", lead.id)
        lead.status = "FAILED"
        lead.error_message = str(e)
        lead.updated_at = datetime.utcnow()
    db.commit()
    lead = _load_lead(db, lead_id)

    return {
        "lead_id": lead.id,
        "status": lead.status,
        "error_message": getattr(lead, "error_message", None),
        "has_json": bool(getattr(lead, "estimate_json", None)),
        "has_html": bool(getattr(lead, "estimate_html_key", None)),
        "updated_at": getattr(lead, "updated_at", None),
        "tenant_id": getattr(lead, "tenant_id", None),
        "vertical": getattr(lead, "vertical", None),
        "files_count": db.query(LeadFile).filter(LeadFile.lead_id == lead.id).count(),
    }


# =========================
# PUBLISH (sync compute)
# =========================
@router.post("/publish/{lead_id}")
def publish_quote(lead_id: int, db: Session = Depends(get_db)):
    lead = _load_lead(db, lead_id)

    inc("publish_requests_total")
    logger.info("LEAD %s publish_requested status=%s", lead.id, lead.status)

    # Idempotent: al klaar -> direct terug
    if lead.status in ("SUCCEEDED", "NEEDS_REVIEW"):
        inc("publish_idempotent_total")
        return {
            "lead_id": lead.id,
            "status": lead.status,
            "next": {
                "status": f"/quotes/{lead.id}/status",
                "json": f"/quotes/{lead.id}/json",
                "html": f"/quotes/{lead.id}/html",
            },
        }

    # Als al bezig -> direct terug
    if lead.status == "RUNNING":
        inc("publish_already_running_total")
        return {
            "lead_id": lead.id,
            "status": lead.status,
            "next": {"status": f"/quotes/{lead.id}/status"},
        }

    files = db.query(LeadFile).filter(LeadFile.lead_id == lead.id).all()
    if not files:
        _set_failed(db, lead, "No files attached to lead")

    # FASE 3 preflight vóór RUNNING
    try:
        _preflight_uploads_or_fail(lead, files)
    except Exception as e:
        _set_failed(db, lead, str(e))

    # RUNNING
    lead.status = "RUNNING"
    lead.error_message = None
    lead.updated_at = datetime.utcnow()
    print("PUBLISH_SAVE lead.id:", lead.id, "lead.tenant_id:", lead.tenant_id)

    db.commit()

    db.refresh(lead)
    print("PUBLISH_DB lead.estimate_html_key:", lead.estimate_html_key)

    inc("quotes_running_total")
    logger.info("LEAD %s status=RUNNING files=%s", lead.id, len(files))

    try:
        vertical_id = (lead.vertical or "paintly").strip() or "paintly"
        # backward compat:
        if vertical_id == "painters_us":
            vertical_id = "paintly"
        lead.vertical = vertical_id
        db.commit()

        v = get_vertical(vertical_id)

        inc("compute_started_total")
        logger.info(
            "LEAD %s compute_quote START vertical=%s tenant=%s",
            lead.id,
            lead.vertical,
            lead.tenant_id,
        )
        raw_result = v.compute_quote(db, lead.id)
        logger.info("LEAD %s compute_quote END", lead.id)
        print("RAW_RESULT:", raw_result)

        estimate_dict, html_key, needs_review = _normalize_compute_result(raw_result)
        if not html_key:
            raise RuntimeError("compute_quote did not return an estimate_html_key")

        # ✅ normalize html_key: remove accidental tenant prefix
        tenant_id = (lead.tenant_id or "").strip() or "default"
        html_key = _strip_tenant_prefix(tenant_id, html_key)

        lead.estimate_json = json.dumps(estimate_dict, ensure_ascii=False, default=str)
        lead.estimate_html_key = html_key
        lead.status = "NEEDS_REVIEW" if needs_review else "SUCCEEDED"
        lead.updated_at = datetime.utcnow()
        db.commit()

        if lead.status == "NEEDS_REVIEW":
            inc("quotes_needs_review_total")
        else:
            inc("quotes_succeeded_total")

        logger.info(
            "LEAD %s status=%s html_key=%s",
            lead.id,
            lead.status,
            lead.estimate_html_key,
        )

        return {
            "lead_id": lead.id,
            "status": lead.status,
            "next": {
                "status": f"/quotes/{lead.id}/status",
                "json": f"/quotes/{lead.id}/json",
                "html": f"/quotes/{lead.id}/html",
            },
        }

    except Exception as e:
        # keep exception details visible for internal debugging
        lead.status = "FAILED"
        lead.error_message = str(e)
        lead.updated_at = datetime.utcnow()
        db.commit()

        inc("quotes_failed_total")
        logger.exception("LEAD %s publish_failed", lead.id)

        raise


# =========================
# ARTIFACTS
# =========================
@router.get("/{lead_id}/json")
def quote_json(lead_id: int, db: Session = Depends(get_db)):
    lead = _load_lead(db, lead_id)
    if not getattr(lead, "estimate_json", None):
        raise HTTPException(status_code=404, detail="No estimate yet")
    return json.loads(lead.estimate_json)


@router.get("/{lead_id}/html")
def quote_html(lead_id: int, db: Session = Depends(get_db)):
    lead = _load_lead(db, lead_id)

    if lead.status not in ("SUCCEEDED", "NEEDS_REVIEW"):
        raise HTTPException(
            status_code=409, detail=f"Quote not ready. Status={lead.status}"
        )

    key = (getattr(lead, "estimate_html_key", None) or "").strip()
    if not key:
        raise HTTPException(status_code=404, detail="No HTML estimate stored")

    tenant_id = str((lead.tenant_id or "").strip() or "default")
    key = _strip_tenant_prefix(tenant_id, key)

    storage = get_storage()

    # Prefer presigned (works with private buckets)
    if hasattr(storage, "presigned_get_url"):
        url = storage.presigned_get_url(
            tenant_id=tenant_id,
            key=key,
            expires_seconds=3600,
        )
    else:
        url = storage.public_url(tenant_id=tenant_id, key=key)

    inc("quote_html_redirects_total")
    return RedirectResponse(url, status_code=302)
