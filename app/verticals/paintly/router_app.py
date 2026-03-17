# app/routers/router_app.py
from __future__ import annotations

import secrets
import uuid
import datetime as dt
from zoneinfo import ZoneInfo
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import datetime, timezone, timedelta
import logging
import json

from fastapi import BackgroundTasks
from fastapi import APIRouter, Depends, HTTPException, Request, Form, Query
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, func, or_
from sqlalchemy.orm import Session

from app.auth.deps import require_user_html
from app.db import get_db
from app.models.lead import Lead
from app.models.job import Job
from app.models.user import User
from app.models.tenant import Tenant
from app.models.tenant_settings import TenantSettings
from app.services.storage import get_storage, get_text
from app.models.lead import LeadFile
from app.models.upload_record import UploadRecord, UploadStatus

from app.core.settings import settings
from app.dependencies import tenant_service
from app.verticals.paintly.email_render import render_estimate_ready_email
from app.verticals.paintly.estimate_email import (
    send_estimate_ready_email_to_customer,
)


router = APIRouter(
    prefix="/app",
    tags=["paintly_app"],
    dependencies=[Depends(require_user_html)],
)
templates = Jinja2Templates(directory="app/verticals/paintly/templates")

ALLOWED_JOB_STATUSES = {"NEW", "SCHEDULED", "IN_PROGRESS", "DONE", "CANCELLED"}

logger = logging.getLogger(__name__)


# -------------------------
# Tenant / UI context helpers
# -------------------------
def _resolve_company_name_and_tenant(
    tenant_id: str,
    db: Session,
) -> tuple[str, Tenant | TenantSettings | None]:
    """
    Resolve tenant settings + human-friendly company name.

    Priority:
    1) tenant.company_name
    2) tenant.name
    3) "Paintly"
    """
    company_name: str | None = None
    source_obj: Tenant | TenantSettings | None = None

    # 1) Try DB Tenant table (authoritative for onboarded accounts)
    try:
        tenant_db = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    except Exception:
        tenant_db = None

    if tenant_db is not None:
        source_obj = tenant_db
        for attr in ("company_name", "name"):
            val = getattr(tenant_db, attr, None)
            if isinstance(val, str) and val.strip():
                company_name = val.strip()
                break

    # 2) Fallback: in-memory TenantSettings (legacy JSON config)
    if company_name is None:
        try:
            ts = tenant_service.get_tenant(tenant_id)
        except Exception:
            ts = None

        if ts is not None:
            if source_obj is None:
                source_obj = ts
            for attr in ("company_name", "name"):
                val = getattr(ts, attr, None)
                if isinstance(val, str) and val.strip():
                    company_name = val.strip()
                    break

    if not company_name:
        company_name = "Aether Engine"

    return company_name, source_obj


def _dashboard_context(
    request: Request,
    current_user: User,
    db: Session,
    extra: dict | None = None,
) -> dict:
    """
    Shared context for all internal Paintly app templates.
    Ensures multi-tenant company branding per request.
    """
    raw_tenant_id = getattr(current_user, "tenant_id", None)
    tenant_id = str(raw_tenant_id) if raw_tenant_id is not None else "default"

    company_name, tenant_obj = _resolve_company_name_and_tenant(tenant_id, db)

    ctx: dict = {
        "request": request,
        "tenant": tenant_obj,
        "company_name": company_name,
    }
    if extra:
        ctx.update(extra)
    return ctx


# -------------------------
# Time & money helpers
# -------------------------
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _safe_tz(tz_name: str | None) -> str:
    tz = (tz_name or "").strip()
    if not tz:
        return "Europe/Amsterdam"
    try:
        ZoneInfo(tz)
        return tz
    except Exception:
        return "Europe/Amsterdam"


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


def _safe_decimal(val: object) -> Decimal | None:
    """Best-effort conversion to Decimal without raising."""
    if val is None:
        return None
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError):
        return None


def _fmt_eur(amount: Decimal | None) -> str | None:
    """Simple EUR formatting for internal UI only."""
    if amount is None:
        return None
    quantized = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    # Basic European-style formatting: 1 234,56
    s = f"{quantized:,.2f}"
    s = s.replace(",", "_").replace(".", ",").replace("_", ".")
    return f"€ {s}"


def _apply_overrides_to_estimate_dict(estimate: dict, overrides: dict) -> dict:
    """
    Build an override-aware copy of the pricing estimate dict.
    Applies manual_total / discount_percent into totals + meta
    so that rendered HTML reflects the internal override UI.
    """
    estimate = dict(estimate or {})
    pricing = estimate  # render_estimate_html expects pricing at top-level

    overrides = dict(overrides or {})
    manual_total = overrides.get("manual_total")
    discount_percent = overrides.get("discount_percent")

    totals = dict(pricing.get("totals") or {})

    # Base total (incl. VAT) from existing estimate
    base_total_incl = totals.get("grand_total") or totals.get("pre_tax") or 0
    try:
        total_dec = Decimal(str(base_total_incl))
    except Exception:
        total_dec = Decimal("0")

    # Apply discount % if present and no explicit manual_total
    if manual_total is None and discount_percent is not None:
        try:
            disc = Decimal(str(discount_percent))
            if disc > 0:
                if disc > 100:
                    disc = Decimal("100")
                factor = (Decimal("100") - disc) / Decimal("100")
                total_dec = (total_dec * factor).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
        except Exception:
            # keep base total on parse errors
            pass

    # If manual_total is provided, it wins over discount_percent
    if manual_total is not None:
        try:
            total_dec = Decimal(str(manual_total)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        except Exception:
            # fall back to original total on parse errors
            pass

    # Derive VAT breakdown from total_dec using pricing's vat_rate if present
    vat_rate = pricing.get("vat_rate")
    if vat_rate is None:
        vat_rate = pricing.get("tax_rate")
    try:
        vat_rate_dec = (
            Decimal(str(vat_rate)) if vat_rate is not None else Decimal("0.21")
        )
    except Exception:
        vat_rate_dec = Decimal("0.21")

    if total_dec <= 0:
        # nothing usable → return original estimate untouched
        return estimate

    # Reverse-calc excl VAT + VAT amount from total incl.
    one_plus = Decimal("1") + vat_rate_dec
    subtotal_excl = (total_dec / one_plus).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    vat_amount = (total_dec - subtotal_excl).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    totals["pre_tax"] = float(subtotal_excl)
    totals["grand_total"] = float(total_dec)
    pricing["totals"] = totals

    # Surface overrides + explicit override_total_incl_vat in meta
    meta = dict(pricing.get("meta") or {})
    meta["overrides"] = overrides
    meta["override_total_incl_vat"] = float(total_dec)

    # If a manual total or discount was applied, treat this estimate as
    # manually finalized: clear AI review flags so the public quote shows
    # a concrete price instead of "review required"/"nader te bepalen".
    if manual_total is not None or discount_percent is not None:
        pricing["needs_review"] = False
        meta["needs_review"] = False
        meta["needs_review_reasons"] = []
        meta["review_reasons"] = []
        if isinstance(pricing.get("review_reasons"), list):
            pricing["review_reasons"] = []

    pricing["meta"] = meta

    # Debug log adjusted totals for verification
    logger.info(
        "APPLY_OVERRIDES_RESULT overrides=%r totals=%r meta_total=%r",
        overrides,
        totals,
        meta.get("override_total_incl_vat"),
    )

    return pricing


def render_quote_html_for_lead(lead: Lead, overrides: dict) -> tuple[str | None, bool]:
    """
    Helper used after saving manual overrides.
    Re-renders estimate HTML from lead.estimate_json + overrides,
    writes it to storage and returns the new html_key.
    """
    from app.verticals.paintly.render_estimate import render_estimate_html

    raw_est = getattr(lead, "estimate_json", None)
    if not raw_est:
        logger.warning(
            "RENDER_QUOTE_HTML_FOR_LEAD_SKIPPED_NO_JSON lead_id=%s html_key=%r",
            getattr(lead, "id", None),
            getattr(lead, "estimate_html_key", None),
        )
        return None, False

    try:
        estimate_dict = json.loads(raw_est)
        if not isinstance(estimate_dict, dict):
            raise TypeError("estimate_json not a dict")
    except Exception:
        logger.exception(
            "RENDER_QUOTE_HTML_FOR_LEAD_PARSE_FAILED lead_id=%s",
            getattr(lead, "id", None),
        )
        return None, False

    logger.info(
        "RENDER_QUOTE_HTML_FOR_LEAD_CALLED lead_id=%s old_html_key=%r",
        getattr(lead, "id", None),
        getattr(lead, "estimate_html_key", None),
    )

    # Apply overrides into pricing totals
    estimate_with_overrides = _apply_overrides_to_estimate_dict(
        estimate_dict, overrides
    )

    logger.info(
        "RENDER_QUOTE_HTML_FOR_LEAD_AFTER_APPLY lead_id=%s totals=%r meta=%r",
        getattr(lead, "id", None),
        (estimate_with_overrides.get("totals") or {}),
        (estimate_with_overrides.get("meta") or {}),
    )

    # Render fresh HTML
    html = render_estimate_html(estimate_with_overrides)

    storage = get_storage()
    today = dt.date.today().isoformat()
    filename = f"estimate_{lead.id}_{uuid.uuid4().hex}.html"
    new_key = f"leads/{lead.id}/estimates/{today}/{filename}"

    storage.save_bytes(
        tenant_id=str(lead.tenant_id),
        key=new_key,
        data=html.encode("utf-8"),
        content_type="text/html; charset=utf-8",
    )

    logger.info(
        "RENDER_QUOTE_HTML_FOR_LEAD_DONE lead_id=%s old_html_key=%r new_html_key=%r",
        getattr(lead, "id", None),
        getattr(lead, "estimate_html_key", None),
        new_key,
    )

    return new_key, True


def get_estimate_overrides(lead: Lead) -> dict:
    """
    Safely parse estimate_overrides_json from a Lead.
    Never raises; returns {} on any error or missing payload.
    """
    raw = getattr(lead, "estimate_overrides_json", None)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except Exception:
        return {}
    return {}


def get_effective_total(lead: Lead) -> Decimal | None:
    """
    Compute override-aware total (incl. VAT) for internal display:
    - If overrides.manual_total present and valid -> use that.
    - Else if overrides.discount_percent present -> apply to base total_incl_vat from estimate_json.
    - Else fall back to base total_incl_vat from estimate_json.
    - Returns None if no usable total.
    """
    overrides = get_estimate_overrides(lead)

    manual_total = _safe_decimal(overrides.get("manual_total"))
    if manual_total is not None:
        return manual_total

    # Parse estimate_json for base total
    base_total: Decimal | None = None
    raw_est = getattr(lead, "estimate_json", None)
    if raw_est:
        try:
            est = json.loads(raw_est)
            if isinstance(est, dict):
                # canonical path used by paintly render_estimate: pricing.meta.vat.total_incl_vat
                totals = est.get("totals") or {}
                vat_block = est.get("vat") or {}
                # prefer vat.total_incl_vat if present, else totals.grand_total, else totals.pre_tax
                for candidate in [
                    vat_block.get("total_incl_vat"),
                    totals.get("grand_total"),
                    totals.get("pre_tax"),
                ]:
                    base_total = _safe_decimal(candidate)
                    if base_total is not None:
                        break
        except Exception:
            base_total = None

    if base_total is None:
        return None

    discount = overrides.get("discount_percent")
    discount_dec = _safe_decimal(discount)
    if discount_dec is None:
        return base_total

    if discount_dec <= 0:
        return base_total

    # Cap at 100% to avoid negative totals
    if discount_dec > 100:
        discount_dec = Decimal("100")

    factor = (Decimal("100") - discount_dec) / Decimal("100")
    return (base_total * factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


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
        return {"label": "Bekijk offerte", "href": f"/app/leads/{lead.id}"}

    # Alleen SUCCEEDED mag verstuurd worden; NEEDS_REVIEW blokkeert send.
    if lead_status == "SUCCEEDED":
        return {
            "label": "Send estimate",
            "href": f"/app/leads/{lead.id}/send",
            "method": "POST",
        }

    if lead_status == "SENT":
        return (
            {"label": "Open publieke offerte", "href": f"/e/{lead.public_token}"}
            if has_public
            else {"label": "Bekijk offerte", "href": f"/app/leads/{lead.id}"}
        )

    if lead_status == "VIEWED":
        return (
            {"label": "Follow up (open)", "href": f"/e/{lead.public_token}"}
            if has_public
            else {"label": "Bekijk offerte", "href": f"/app/leads/{lead.id}"}
        )

    if lead_status == "ACCEPTED":
        if not job:
            return {"label": "Bekijk offerte", "href": f"/app/leads/{lead.id}"}
        js = (job.status or "").upper()
        if js in {"NEW", "SCHEDULED", "IN_PROGRESS"}:
            return {"label": "Update job", "href": f"/app/leads/{lead.id}#job"}
        return {"label": "Bekijk offerte", "href": f"/app/leads/{lead.id}"}

    return {"label": "Bekijk offerte", "href": f"/app/leads/{lead.id}"}


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

    context = _dashboard_context(
        request,
        current_user,
        db,
        {"kpis": kpis, "jobs": jobs_vm, "leads": leads_vm},
    )
    return templates.TemplateResponse("app/dashboard.html", context)


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

    context = _dashboard_context(
        request,
        current_user,
        db,
        {"leads": rows},
    )
    return templates.TemplateResponse("app/leads_list.html", context)


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

    intake_payload_dict = {}

    if lead.intake_payload:
        try:
            intake_payload_dict = json.loads(lead.intake_payload)
        except Exception:
            intake_payload_dict = {}

    # Manual estimate overrides (internal-only)
    overrides = get_estimate_overrides(lead)
    effective_total = get_effective_total(lead)
    effective_total_display = _fmt_eur(effective_total) if effective_total is not None else None

    job = (
        db.query(Job)
        .filter(Job.lead_id == lead.id, Job.tenant_id == str(current_user.tenant_id))
        .first()
    )

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

    # -------------------------
    # Photo previews (MVP)
    # -------------------------
    photo_previews: list[dict] = []
    try:
        uploads = (
            db.query(UploadRecord)
            .filter(
                UploadRecord.tenant_id == lead.tenant_id,
                UploadRecord.lead_id == lead.id,
                UploadRecord.status.in_([UploadStatus.uploaded, "uploaded"]),
            )
            .order_by(UploadRecord.id.desc())
            .all()
        )

        storage = get_storage()

        for u in uploads:
            # alleen afbeeldingen tonen
            if hasattr(u, "is_image") and not u.is_image:
                continue

            object_key = (getattr(u, "object_key", "") or "").strip()
            if not object_key:
                continue

            # object_key staat meestal als "<tenant_id>/..."; storage verwacht key zonder tenant prefix
            tenant_prefix = f"{lead.tenant_id}/"
            key = (
                object_key[len(tenant_prefix) :]
                if object_key.startswith(tenant_prefix)
                else object_key
            )

            try:
                if hasattr(storage, "presigned_get_url"):
                    url = storage.presigned_get_url(
                        tenant_id=str(lead.tenant_id),
                        key=key,
                        expires_seconds=3600,
                    )
                else:
                    url = storage.public_url(
                        tenant_id=str(lead.tenant_id),
                        key=key,
                    )

                name = key.split("/")[-1] if key else ""
                photo_previews.append({"url": url, "name": name})
            except Exception:
                # nooit hard falen op previews
                continue
    except Exception:
        # bij problemen met query/storage gewoon geen foto's tonen
        photo_previews = []

    # -------------------------
    # Quote UI flags (MVP)
    # -------------------------
    has_estimate = bool(getattr(lead, "estimate_html_key", None))
    raw_status = (getattr(lead, "status", "") or "").upper()

    if not has_estimate:
        quote_status = "none"
    elif raw_status == "ACCEPTED":
        quote_status = "accepted"
    elif raw_status == "NEEDS_REVIEW":
        quote_status = "review"
    elif raw_status in {"SENT", "VIEWED"}:
        quote_status = "sent"
    else:
        quote_status = "generated"

    public_quote_url = public_url_for(request, lead)

    can_generate = not has_estimate
    can_view = has_estimate
    # Only allow sending if estimate is fully succeeded (not in review) and email present
    can_send = (
        has_estimate
        and raw_status == "SUCCEEDED"
        and bool((getattr(lead, "email", "") or "").strip())
    )
    # Allow regeneration while not accepted
    can_regenerate = has_estimate and raw_status != "ACCEPTED"

    quote_ui = {
        "has_estimate": has_estimate,
        "quote_status": quote_status,
        "can_generate": can_generate,
        "can_view": can_view,
        "can_regenerate": can_regenerate,
        "can_send": can_send,
        "public_quote_url": public_quote_url,
    }

    context = _dashboard_context(
        request,
        current_user,
        db,
        {
            "lead": lead,
            "job": job,
            "intake_payload_dict": intake_payload_dict,
            "quote_ui": quote_ui,
            "photo_previews": photo_previews,
            "tz_name": tz_name,
            "scheduled_input_value": scheduled_input_value,
            "scheduled_display": scheduled_display,
            "started_display": started_display,
            "done_display": done_display,
            "estimate_overrides": overrides,
            "effective_total_display": effective_total_display,
        },
    )
    return templates.TemplateResponse("app/lead_detail.html", context)


@router.get("/leads/{lead_id}/estimate")
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

    logger.info(
        "APP_LEAD_ESTIMATE_ROUTE lead_id=%s html_key=%r",
        getattr(lead, "id", None),
        html_key,
    )

    storage = get_storage()

    # ✅ Redirect to presigned URL (fresh each time)
    if hasattr(storage, "presigned_get_url"):
        url = storage.presigned_get_url(
            tenant_id=str(current_user.tenant_id),
            key=html_key,
            expires_seconds=300,
        )
        resp = RedirectResponse(url=url, status_code=302)
        resp.headers["Cache-Control"] = "no-store"
        return resp

    # fallback: public url (if you don't have presign)
    url = storage.public_url(tenant_id=str(current_user.tenant_id), key=html_key)
    resp = RedirectResponse(url=url, status_code=302)
    resp.headers["Cache-Control"] = "no-store"
    return resp


from fastapi import BackgroundTasks


@router.post("/leads/{lead_id}/send")
def send_estimate(
    lead_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user_html),
):
    logger.warning("SEND_ESTIMATE_HIT lead_id=%s", lead_id)

    lead = (
        db.query(Lead)
        .filter(Lead.id == lead_id, Lead.tenant_id == str(current_user.tenant_id))
        .first()
    )
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    if not lead.estimate_html_key:
        # Geen offerte beschikbaar om te versturen -> nette melding op lead detail
        return RedirectResponse(
            url=f"/app/leads/{lead_id}?send_error=no_estimate",
            status_code=303,
        )

    # ensure public token
    if not lead.public_token:
        lead.public_token = secrets.token_hex(16)

    # build public quote url
    base = (settings.APP_PUBLIC_BASE_URL or str(request.base_url)).rstrip("/")
    quote_url = f"{base}/e/{lead.public_token}"

    # must have email
    to_email = (getattr(lead, "email", "") or "").strip()
    if not to_email:
        # Geen klant e-mail -> nette melding op lead detail
        return RedirectResponse(
            url=f"/app/leads/{lead_id}?send_error=no_email",
            status_code=303,
        )

    company_name = "Paintly"
    customer_name = getattr(lead, "name", "") or ""

    async def _send():
        logger.info("Sending estimate email to %s", to_email)
        await send_estimate_ready_email_to_customer(
            to_email=to_email,
            customer_name=customer_name,
            quote_url=quote_url,
            company_name=company_name,
            lead_id=lead.id,
            tenant_id=str(lead.tenant_id),
        )

    background_tasks.add_task(_send)

    # mark as sent
    lead.status = "SENT"
    lead.sent_at = _utcnow()

    db.add(lead)
    db.commit()

    response = RedirectResponse(
        url=f"/app/leads/{lead_id}?sent=1",
        status_code=303,
    )
    response.background = background_tasks
    return response


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

    context = _dashboard_context(
        request,
        current_user,
        db,
        {
            "jobs": rows,
            "counts": counts,
            "active_status": status_norm,
        },
    )
    return templates.TemplateResponse("app/jobs_list.html", context)


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

    context = _dashboard_context(
        request,
        current_user,
        db,
        {
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
    return templates.TemplateResponse("app/calendar_week.html", context)


@router.get("/reviews", response_class=HTMLResponse)
def app_reviews_list(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user_html),
):
    tenant = str(current_user.tenant_id)

    # Gebruik dezelfde businessregel als derive_status:
    # - expliciete status NEEDS_REVIEW
    # - of needs_review_hard-flag actief
    leads = (
        db.query(Lead)
        .filter(
            or_(
                Lead.status == "NEEDS_REVIEW",
                getattr(Lead, "needs_review_hard", None) == True,  # noqa: E712
            ),
            or_(Lead.tenant_id == tenant, Lead.tenant_id == "public"),
        )
        # MVP: sorteer simpel en robuust op primaire sleutel
        .order_by(desc(Lead.id))
        .limit(200)
        .all()
    )

    context = _dashboard_context(
        request,
        current_user,
        db,
        {"leads": leads},
    )
    return templates.TemplateResponse("app/reviews_list.html", context)


@router.get("/reviews/{lead_id}", response_class=HTMLResponse)
def app_review_detail(
    request: Request,
    lead_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user_html),
):
    lead = (
        db.query(Lead)
        .filter(
            Lead.id == lead_id,
            Lead.tenant_id == str(current_user.tenant_id),
        )
        .first()
    )
    if not lead:
        # DEBUG: bestaat lead_id überhaupt (los van tenant)?
        lead_any = db.query(Lead).filter(Lead.id == lead_id).first()
        if lead_any:
            raise HTTPException(
                status_code=404,
                detail=f"Lead exists but tenant mismatch. lead.tenant_id={lead_any.tenant_id} user.tenant_id={str(current_user.tenant_id)}",
            )
        raise HTTPException(status_code=404, detail="Lead id not found in DB")

    # reasons MVP: uit estimate_json.meta.needs_review_reasons
    reasons = []
    try:
        if lead.estimate_json:
            est = json.loads(lead.estimate_json)
            reasons = (est.get("meta") or {}).get("needs_review_reasons") or []
    except Exception:
        reasons = []

    # uploads (upload_records) voor debug/preview
    uploads = (
        db.query(UploadRecord)
        .filter(
            UploadRecord.tenant_id == lead.tenant_id,
            UploadRecord.lead_id == lead.id,
            UploadRecord.status.in_([UploadStatus.uploaded, "uploaded"]),
        )
        .order_by(UploadRecord.id.desc())
        .all()
    )

    storage = get_storage()

    # photo preview urls (uit upload_records.object_key)
    photo_urls = []
    for u in uploads:
        object_key = (getattr(u, "object_key", "") or "").strip()
        if not object_key:
            continue

        # object_key staat bij jou als "public/uploads/...."
        # storage verwacht meestal key ZONDER tenant prefix:
        tenant_prefix = f"{lead.tenant_id}/"
        key = (
            object_key[len(tenant_prefix) :]
            if object_key.startswith(tenant_prefix)
            else object_key
        )

        try:
            if hasattr(storage, "presigned_get_url"):
                url = storage.presigned_get_url(
                    tenant_id=str(lead.tenant_id),
                    key=key,
                    expires_seconds=3600,
                )
            else:
                url = storage.public_url(
                    tenant_id=str(lead.tenant_id),
                    key=key,
                )
            photo_urls.append(url)
        except Exception:
            # nooit hard failen op preview
            continue

    # estimate preview url
    estimate_preview_url = None
    html_key = (getattr(lead, "estimate_html_key", None) or "").strip()
    if html_key:
        try:
            if hasattr(storage, "presigned_get_url"):
                estimate_preview_url = storage.presigned_get_url(
                    tenant_id=str(lead.tenant_id),
                    key=html_key,
                    expires_seconds=300,
                )
            else:
                estimate_preview_url = storage.public_url(
                    tenant_id=str(lead.tenant_id),
                    key=html_key,
                )
        except Exception:
            estimate_preview_url = None

    can_preview = bool(html_key)

    intake = {}
    try:
        if getattr(lead, "intake_payload", None):
            intake = json.loads(lead.intake_payload)
    except Exception:
        intake = {}

    context = _dashboard_context(
        request,
        current_user,
        db,
        {
            "lead": lead,
            "reasons": reasons,
            "uploads": uploads,
            "photo_urls": photo_urls,
            "can_preview": can_preview,
            "estimate_preview_url": estimate_preview_url,
            "intake": intake,
        },
    )
    return templates.TemplateResponse("app/review_detail.html", context)


@router.post("/reviews/{lead_id}/generate-estimate")
def app_review_generate_estimate(
    lead_id: str,
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

    # Reset -> laat quotes status page opnieuw publishen via autostart JS
    lead.status = "NEW"
    lead.error_message = None
    lead.estimate_json = None
    lead.estimate_html_key = None
    lead.updated_at = _utcnow()

    # ✅ Manual override flag
    payload = {}
    try:
        if getattr(lead, "intake_payload", None):
            payload = json.loads(lead.intake_payload)
    except Exception:
        payload = {}

    payload["manual_override"] = True
    lead.intake_payload = json.dumps(payload, ensure_ascii=False)

    db.add(lead)
    db.commit()

    return RedirectResponse(
        url=f"/quotes/{lead_id}/status?autostart=1", status_code=303
    )


@router.post("/app/reviews/{lead_id}/generate-estimate")
def app_review_generate_estimate(
    lead_id: str,
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

    # Reset -> laat quotes status page opnieuw publishen via autostart JS
    lead.status = "NEW"
    lead.error_message = None
    lead.estimate_json = None
    lead.estimate_html_key = None
    lead.updated_at = _utcnow()

    # ✅ Manual override flag
    payload = {}
    try:
        if getattr(lead, "intake_payload", None):
            payload = json.loads(lead.intake_payload)
    except Exception:
        payload = {}

    payload["manual_override"] = True
    lead.intake_payload = json.dumps(payload, ensure_ascii=False)

    db.add(lead)
    db.commit()

    return RedirectResponse(
        url=f"/quotes/{lead_id}/status?autostart=1", status_code=303
    )


@router.post("/reviews/{lead_id}/overrides")
def app_review_save_overrides(
    lead_id: str,
    square_meters: float | None = Form(default=None),
    job_type: str | None = Form(default=None),
    project_description: str | None = Form(default=None),
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

    payload = {}
    try:
        if getattr(lead, "intake_payload", None):
            payload = json.loads(lead.intake_payload)
    except Exception:
        payload = {}

    # -------------------------
    # ✅ Area override (EU: m²)
    # -------------------------
    if square_meters is not None:
        sqm = float(square_meters)

        # keep both keys for compatibility
        payload["square_meters"] = sqm
        payload["area_sqm"] = sqm

        if hasattr(lead, "square_meters"):
            lead.square_meters = sqm

        # cleanup old/US keys (do NOT remove square_meters)
        payload.pop("sqft", None)
        payload.pop("sqm", None)

    # -------------------------
    # Job type override
    # -------------------------
    if job_type:
        payload["job_type"] = job_type
        if hasattr(lead, "job_type"):
            lead.job_type = job_type

    # -------------------------
    # Description override
    # -------------------------
    if project_description is not None:
        payload["project_description"] = project_description
        if hasattr(lead, "notes"):
            lead.notes = project_description

    # -------------------------
    # ✅ Manual override flag (so needs_review can be skipped)
    # -------------------------
    payload["manual_override"] = True

    # Persist updated payload
    lead.intake_payload = json.dumps(payload, ensure_ascii=False)

    db.add(lead)
    db.commit()
    db.refresh(lead)

    return RedirectResponse(url=f"/app/reviews/{lead.id}", status_code=303)


@router.get("/leads/{lead_id}/edit-estimate", response_class=HTMLResponse)
def edit_estimate_get(
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

    overrides = get_estimate_overrides(lead)
    context = _dashboard_context(
        request,
        current_user,
        db,
        {"lead": lead, "overrides": overrides},
    )
    return templates.TemplateResponse("app/estimate_edit.html", context)


@router.post("/leads/{lead_id}/edit-estimate")
def edit_estimate_post(
    lead_id: int,
    public_notes: str | None = Form(default=None),
    discount_percent: float | None = Form(default=None),
    manual_total: float | None = Form(default=None),
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

    overrides = get_estimate_overrides(lead)

    old_html_key = getattr(lead, "estimate_html_key", None)
    has_json = bool(getattr(lead, "estimate_json", None))
    logger.info(
        "EDIT_ESTIMATE_POST_START lead_id=%s old_html_key=%r has_estimate_json=%s",
        getattr(lead, "id", None),
        old_html_key,
        has_json,
    )

    overrides["public_notes"] = (public_notes or "").strip()
    overrides["discount_percent"] = (
        float(discount_percent) if discount_percent is not None else None
    )
    overrides["manual_total"] = (
        float(manual_total) if manual_total is not None else None
    )

    lead.estimate_overrides_json = json.dumps(overrides, ensure_ascii=False)
    lead.updated_at = _utcnow()

    # If a manual total or discount is applied, also mark the intake payload
    # as manually overridden so future pipeline runs can skip AI-driven review.
    if overrides["manual_total"] is not None or overrides["discount_percent"] is not None:
        try:
            payload = {}
            raw_payload = getattr(lead, "intake_payload", None)
            if isinstance(raw_payload, str) and raw_payload.strip():
                payload = json.loads(raw_payload)
            elif isinstance(raw_payload, dict):
                payload = dict(raw_payload)

            payload["manual_override"] = True
            lead.intake_payload = json.dumps(payload, ensure_ascii=False)
        except Exception:
            # Non-fatal: if we can't update intake_payload, continue with overrides only.
            pass

    # Re-render quote HTML with overrides applied, if possible
    new_html_key, rendered = render_quote_html_for_lead(lead, overrides)
    if rendered and new_html_key:
        lead.estimate_html_key = new_html_key

    db.add(lead)
    db.commit()
    db.refresh(lead)

    logger.info(
        "EDIT_ESTIMATE_POST_DONE lead_id=%s old_html_key=%r new_html_key=%r rendered=%s",
        getattr(lead, "id", None),
        old_html_key,
        getattr(lead, "estimate_html_key", None),
        rendered,
    )

    return RedirectResponse(url=f"/app/leads/{lead_id}", status_code=303)
