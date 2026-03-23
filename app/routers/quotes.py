# app/routers/quotes.py
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, Tuple

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, require_user_html
from app.db import get_db
from app.models import Lead, LeadFile, Tenant
from app.models.calendar_connection import CalendarConnection
from app.models.quote_calendar_link import QuoteCalendarLink
from app.models.user import User
from app.services.storage import get_storage, head_ok, MAX_BYTES, ALLOWED_CONTENT_TYPES
from app.services.metrics import inc  # ✅ FASE 6 metrics
from app.verticals.paintly.calendar_ics import (
    build_quote_calendar_payload,
    build_quote_ics,
    build_quote_ics_filename,
)
from app.verticals.paintly.google_calendar_oauth import (
    create_google_calendar_event,
    decrypt_token,
    encrypt_token,
    refresh_access_token,
    token_expiry_from_response,
)
from app.verticals.paintly.google_calendar_quote import build_google_event_payload
from app.verticals.registry import get as get_vertical
from app.core.settings import settings
from app.verticals.paintly.estimate_email import (
    send_estimate_ready_email_to_customer,
)

router = APIRouter(prefix="/quotes", tags=["quotes"])
templates = Jinja2Templates(directory="app/templates")
paintly_templates = Jinja2Templates(directory="app/verticals/paintly/templates")
logger = logging.getLogger(__name__)


async def _send_ready_email_task(
    *,
    to_email: str,
    customer_name: str,
    quote_url: str,
    company_name: str,
    lead_id: str,
    tenant_id: str,
) -> None:
    await send_estimate_ready_email_to_customer(
        to_email=to_email,
        customer_name=customer_name,
        quote_url=quote_url,
        company_name=company_name,
        lead_id=lead_id,
        tenant_id=tenant_id,
    )


def _load_lead(db: Session, lead_id: str) -> Lead:
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
    if key.startswith(prefix):
        return key[len(prefix) :]

    # Backward compatibility: some historic records contain a different
    # tenant prefix (e.g. "public/uploads/..."). For storage checks we
    # normalize to the canonical tenant-less "uploads/..." key format.
    uploads_marker = "uploads/"
    idx = key.find(uploads_marker)
    if idx > 0:
        return key[idx:]

    return key


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
        key = _strip_tenant_prefix(tenant_id, raw_key).lstrip("/")

        # TEMP DEBUG: trace exact preflight inputs and local file resolution.
        local_resolved_path = None
        local_exists = None
        if hasattr(storage, "_full_path"):
            try:
                p = storage._full_path(tenant_id, key)  # type: ignore[attr-defined]
                local_resolved_path = str(p)
                local_exists = bool(p.exists() and p.is_file())
            except Exception:
                local_resolved_path = None
                local_exists = None

        logger.info(
            "PREFLIGHT_DEBUG lead_id=%s tenant_id=%s backend=%s raw_key=%r normalized_key=%r local_path=%r local_exists=%r",
            str(getattr(lead, "id", "")),
            tenant_id,
            type(storage).__name__,
            raw_key,
            key,
            local_resolved_path,
            local_exists,
        )

        ok, meta, err = head_ok(storage, tenant_id, key)

        # LocalStorage fallback: if head_ok says not found but file exists under
        # the exact resolved path, treat it as valid and continue with local meta.
        if (
            not ok
            and err == "head_not_found"
            and hasattr(storage, "_head_local")
            and hasattr(storage, "_full_path")
        ):
            try:
                # Keep normalization identical to upload/vision flow:
                # only strip "{tenant_id}/" when present.
                # Retry using original raw_key too, in case records are mixed.
                candidates = [key]
                raw_norm = raw_key.lstrip("/")
                tenant_prefix = f"{tenant_id}/"
                if raw_norm.startswith(tenant_prefix):
                    raw_norm = raw_norm[len(tenant_prefix) :]
                if raw_norm and raw_norm not in candidates:
                    candidates.append(raw_norm)

                for candidate_key in candidates:
                    p = storage._full_path(tenant_id, candidate_key)  # type: ignore[attr-defined]
                    exists_now = bool(p.exists() and p.is_file())
                    logger.info(
                        "PREFLIGHT_DEBUG_LOCAL_CANDIDATE tenant_id=%s candidate_key=%r local_path=%r exists=%r",
                        tenant_id,
                        candidate_key,
                        str(p),
                        exists_now,
                    )
                    if exists_now:
                        local_meta = storage._head_local(tenant_id, candidate_key)  # type: ignore[attr-defined]
                        if local_meta:
                            ok = True
                            meta = local_meta
                            err = None
                            key = candidate_key
                            logger.info(
                                "PREFLIGHT_DEBUG_LOCAL_FALLBACK_OK tenant_id=%s key=%r local_path=%r",
                                tenant_id,
                                key,
                                str(p),
                            )
                            break
            except Exception:
                pass

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
def quote_status_page(request: Request, lead_id: str, db: Session = Depends(get_db)):
    # UX: de "tweede statuspagina" (quote_status.html) vervangen door één
    # tussenpagina: /processing/{lead_id}. Hierdoor wordt quote_status.html
    # nooit meer gerenderd in de customer flow.
    _ = _load_lead(db, lead_id)
    return RedirectResponse(url=f"/processing/{lead_id}", status_code=303)


@router.get("/{lead_id}/status.json")
def quote_status_json(lead_id: str, db: Session = Depends(get_db)):
    lead = _load_lead(db, lead_id)

    # ✅ server-side autostart: als NEW, start publish
    if lead.status == "NEW":
        logger.info("STATUS_JSON autostart publish lead=%s", lead.id)
        try:
            publish_quote(lead_id=lead.id, background=BackgroundTasks(), db=db)
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
def publish_quote(
    lead_id: str,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    lead = _load_lead(db, lead_id)
    logger.info("PUBLISH_FLOW_START lead=%s", lead.id)

    inc("publish_requests_total")
    logger.info("LEAD %s publish_requested status=%s", lead.id, lead.status)

    # Idempotent: al klaar -> direct naar lead detail offerteview
    if lead.status in ("SUCCEEDED", "NEEDS_REVIEW"):
        inc("publish_idempotent_total")
        return RedirectResponse(
            url=f"/app/leads/{lead.id}/estimate",
            status_code=303,
        )

    # Als al bezig -> direct naar lead detail offerteview
    if lead.status == "RUNNING":
        inc("publish_already_running_total")
        return RedirectResponse(
            url=f"/app/leads/{lead.id}/estimate",
            status_code=303,
        )

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
        logger.info("PUBLISH_FLOW_COMPUTE_DONE lead=%s", lead.id)
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

        # If the quote fully succeeded, send the customer "estimate ready" email
        if lead.status == "SUCCEEDED":
            to_email = (getattr(lead, "email", "") or "").strip()
            if to_email:
                # Ensure public token exists so we can build the /e/{token} link
                if not getattr(lead, "public_token", None):
                    import secrets

                    lead.public_token = secrets.token_hex(16)
                    lead.updated_at = datetime.utcnow()
                    db.add(lead)
                    db.commit()

                base = (settings.APP_PUBLIC_BASE_URL or "").rstrip("/")
                if base:
                    quote_url = f"{base}/e/{lead.public_token}"
                else:
                    quote_url = f"/e/{lead.public_token}"

                customer_name = getattr(lead, "name", "") or ""
                company_name = "Paintly"
                lead_id_value = str(lead.id)
                tenant_id_value = str(getattr(lead, "tenant_id", "") or "")

                background.add_task(
                    _send_ready_email_task,
                    to_email=to_email,
                    customer_name=customer_name,
                    quote_url=quote_url,
                    company_name=company_name,
                    lead_id=lead_id_value,
                    tenant_id=tenant_id_value,
                )

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
        logger.info("PUBLISH_FLOW_DONE lead=%s status=%s", lead.id, lead.status)

        # Na succesvolle compute_quote: redirect direct naar lead detail offerteview
        return RedirectResponse(
            url=f"/app/leads/{lead.id}/estimate",
            status_code=303,
        )

    except Exception as e:
        # keep exception details visible for internal debugging
        lead.status = "FAILED"
        lead.error_message = str(e)
        lead.updated_at = datetime.utcnow()
        db.commit()

        inc("quotes_failed_total")
        logger.exception("LEAD %s publish_failed", lead.id)
        logger.info("PUBLISH_FLOW_FAILED lead=%s", lead.id)

        raise


# =========================
# ARTIFACTS
# =========================
@router.get("/{lead_id}/json")
def quote_json(lead_id: str, db: Session = Depends(get_db)):
    lead = _load_lead(db, lead_id)
    if not getattr(lead, "estimate_json", None):
        raise HTTPException(status_code=404, detail="No estimate yet")
    return json.loads(lead.estimate_json)


@router.get("/{lead_id}/html")
def quote_html(lead_id: str, db: Session = Depends(get_db)):
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


@router.get("/{quote_id}/calendar.ics")
def quote_calendar_ics(
    quote_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user_html),
):
    lead = (
        db.query(Lead)
        .filter(Lead.id == quote_id, Lead.tenant_id == str(current_user.tenant_id))
        .first()
    )
    if not lead:
        raise HTTPException(status_code=404, detail="Quote not found")

    try:
        payload = build_quote_calendar_payload(lead)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    ics_body = build_quote_ics(payload)
    filename = build_quote_ics_filename(quote_id)

    return Response(
        content=ics_body,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


def _create_google_calendar_event_for_quote(
    *,
    quote_id: str,
    db: Session,
    current_user: User,
):
    tenant_id = str(current_user.tenant_id)
    lead = (
        db.query(Lead)
        .filter(Lead.id == quote_id, Lead.tenant_id == tenant_id)
        .first()
    )
    if not lead:
        raise HTTPException(status_code=404, detail="Quote not found")

    connection = (
        db.query(CalendarConnection)
        .filter(
            CalendarConnection.tenant_id == tenant_id,
            CalendarConnection.provider == "google",
        )
        .first()
    )
    if not connection:
        raise HTTPException(status_code=409, detail="Google Calendar is not connected.")

    try:
        payload = build_quote_calendar_payload(lead)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    access_token = decrypt_token(connection.access_token_encrypted)
    expires_at = connection.token_expires_at
    if expires_at is not None:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= datetime.now(UTC):
            if not connection.refresh_token_encrypted:
                raise HTTPException(status_code=409, detail="Google token expired. Reconnect integration.")
            refreshed = refresh_access_token(
                decrypt_token(connection.refresh_token_encrypted)
            )
            refreshed_access = str(refreshed.get("access_token") or "").strip()
            if not refreshed_access:
                raise HTTPException(
                    status_code=409,
                    detail="Failed to refresh Google token. Reconnect integration.",
                )
            access_token = refreshed_access
            connection.access_token_encrypted = encrypt_token(refreshed_access)
            connection.token_expires_at = token_expiry_from_response(refreshed)
            db.add(connection)
            db.commit()

    event_payload = build_google_event_payload(payload)
    event = create_google_calendar_event(
        access_token=access_token,
        calendar_id=connection.calendar_id or "primary",
        event_payload=event_payload,
    )
    event_id = str(event.get("id") or "").strip()
    if not event_id:
        raise HTTPException(status_code=400, detail="Google Calendar event missing id.")
    link = (
        db.query(QuoteCalendarLink)
        .filter(
            QuoteCalendarLink.tenant_id == tenant_id,
            QuoteCalendarLink.quote_id == quote_id,
            QuoteCalendarLink.provider == "google",
        )
        .first()
    )
    if not link:
        link = QuoteCalendarLink(
            tenant_id=tenant_id,
            quote_id=quote_id,
            provider="google",
            external_event_id=event_id,
        )
    else:
        link.external_event_id = event_id
    db.add(link)
    db.commit()
    return {"ok": True, "event_id": event_id, "html_link": event.get("htmlLink")}


@router.post("/{quote_id}/calendar/google")
def create_quote_google_calendar(
    quote_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _create_google_calendar_event_for_quote(
        quote_id=quote_id, db=db, current_user=current_user
    )


@router.post("/{quote_id}/calendar/google/partial", response_class=HTMLResponse)
def create_quote_google_calendar_partial(
    request: Request,
    quote_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        result = _create_google_calendar_event_for_quote(
            quote_id=quote_id,
            db=db,
            current_user=current_user,
        )
        context = {
            "request": request,
            "ok": True,
            "message": "Google Calendar event aangemaakt.",
            "event_id": result.get("event_id"),
            "html_link": result.get("html_link"),
        }
    except HTTPException as exc:
        context = {
            "request": request,
            "ok": False,
            "message": str(exc.detail) if exc.detail else "Kon event niet aanmaken.",
            "event_id": None,
            "html_link": None,
        }
    return paintly_templates.TemplateResponse("app/partials/calendar_feedback.html", context)
