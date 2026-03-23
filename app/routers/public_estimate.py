# app/routers/public_estimate.py
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import logging
import json
from decimal import Decimal, InvalidOperation

from app.core.settings import settings
from app.db import get_db
from app.models.lead import Lead
from app.models.user import User
from app.models.job import Job
from app.services.email_service import send_email, EmailSendError
from app.services.storage import get_storage, get_text, LocalStorage
from app.services.workflow import (
    ensure_job_for_lead,
    mark_lead_accepted,
    mark_lead_viewed,
)
from app.verticals.paintly.email_render import (
    render_estimate_accepted_email,
    render_painter_estimate_accepted_email,
)
from app.workflow.status import apply_workflow

router = APIRouter(prefix="/e", tags=["public_estimate"])
# Alias router for simple customer-friendly quote URL (/q/{public_token})
router_q = APIRouter(prefix="/q", tags=["public_quote"])
paintly_templates = Jinja2Templates(directory="app/verticals/paintly/templates")

logger = logging.getLogger(__name__)


async def send_painter_accept_email(
    *,
    painter_email: str,
    company_name: str,
    lead_name: str,
    lead_email: str,
    lead_phone: str,
    project_description: str,
    square_meters: str,
    job_type: str,
    price_display: str,
    quote_url: str,
    admin_url: str,
) -> None:
    subject = f"Offerte geaccepteerd - {lead_name or 'Onbekende klant'}"

    html_body = render_painter_estimate_accepted_email(
        company_name=company_name,
        lead_name=lead_name,
        lead_email=lead_email,
        lead_phone=lead_phone,
        project_description=project_description,
        square_meters=square_meters,
        job_type=job_type,
        price_display=price_display,
        quote_url=quote_url,
        admin_url=admin_url,
    )

    text_body = (
        "Een klant heeft de offerte geaccepteerd.\n\n"
        f"Klant: {lead_name or '—'}\n"
        f"E-mail: {lead_email or '—'}\n"
        f"Telefoon: {lead_phone or '—'}\n"
        f"Type werk: {job_type or '—'}\n"
        f"Oppervlakte: {square_meters or '—'}\n"
        f"Prijs: {price_display or '—'}\n"
        f"Projectnotities: {project_description or '—'}\n\n"
        f"Dashboard: {admin_url}\n"
        f"Publieke offerte: {quote_url}\n"
    )

    await send_email(
        to=painter_email,
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        tag="painter-accepted",
        metadata={},
    )


def _fmt_price_eur(value: object) -> str:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return "—"
    amount = amount.quantize(Decimal("0.01"))
    s = f"{amount:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"EUR {s}"


def _extract_quote_summary(lead: Lead) -> tuple[str, str, str, str]:
    notes = (getattr(lead, "notes", "") or "").strip()
    square_meters = ""
    job_type = ""
    price_display = "—"
    intake_raw = getattr(lead, "intake_payload", None)
    if isinstance(intake_raw, str) and intake_raw.strip():
        try:
            intake = json.loads(intake_raw)
        except Exception:
            intake = {}
        if isinstance(intake, dict):
            square_meters = str(
                intake.get("square_meters")
                or intake.get("area_sqm")
                or intake.get("sqm")
                or ""
            ).strip()
            job_type = str(intake.get("job_type") or "").strip()
            if not notes:
                notes = str(intake.get("project_description") or "").strip()

    final_price = getattr(lead, "final_price", None)
    if final_price is not None:
        price_display = _fmt_price_eur(final_price)
    else:
        estimate_raw = getattr(lead, "estimate_json", None)
        if isinstance(estimate_raw, str) and estimate_raw.strip():
            try:
                estimate = json.loads(estimate_raw)
            except Exception:
                estimate = {}
            if isinstance(estimate, dict):
                totals = estimate.get("totals") or {}
                value = totals.get("grand_total") or totals.get("pre_tax")
                if value is not None:
                    price_display = _fmt_price_eur(value)

    square_meters_display = f"{square_meters} m2" if square_meters else "—"
    return notes or "—", square_meters_display, job_type or "—", price_display


@router.get("/{token}", response_class=HTMLResponse)
def public_estimate(token: str, request: Request, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.public_token == token).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Not found")

    # DEMO-SAFE OVERRIDE:
    # - Als de lead in NEEDS_REVIEW staat, of als de estimate-meta aangeeft
    #   dat er duidelijke wandschade / heavy prep aanwezig is, tonen we geen
    #   volledige offerte maar een simpele "review vereist"-pagina.
    try:
        status_upper = (lead.status or "").upper()
        meta_reasons = []
        raw_json_lower = ""
        try:
            import json as _json

            raw = getattr(lead, "estimate_json", None)
            if isinstance(raw, str) and raw.strip():
                raw_json_lower = raw.lower()
                est = _json.loads(raw)
                if isinstance(est, dict):
                    meta = est.get("meta") or {}
                    if isinstance(meta, dict):
                        rr = meta.get("needs_review_reasons") or []
                        if isinstance(rr, list):
                            meta_reasons = rr
        except Exception:
            meta_reasons = []

        severe_structural_reasons = {
            "substrate_visible",
            "peeling_wallcovering_detected",
            "repair_work_required",
            "surface_damage_detected",
        }

        # Sterke string-gebaseerde fallback voor demo:
        damage_keywords = [
            "wallpaper",
            "wallpaper_removal",
            "peeling",
            "exposed_plaster",
            "substrate",
            "damaged",
            "repair",
            "heavy_prep",
            "plaster_visible",
            "loose_wallcovering",
        ]
        strong_damage_hit = bool(
            raw_json_lower
            and any(kw in raw_json_lower for kw in damage_keywords)
        )

        meta_has_wall_repair = "wall_repair_or_wallpaper_likely" in meta_reasons

        if (
            (status_upper == "NEEDS_REVIEW")
            and (
                any(r in severe_structural_reasons for r in meta_reasons)
                or meta_has_wall_repair
            )
        ) or strong_damage_hit:
            return HTMLResponse(
                content="""
<!doctype html>
<html lang="nl">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Offerte in review — Paintly</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="min-h-screen bg-slate-50 text-slate-900 antialiased">
  <div class="flex min-h-screen items-center justify-center px-4">
    <div class="w-full max-w-md rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
      <div class="flex items-center gap-3">
        <div class="flex h-10 w-10 items-center justify-center rounded-2xl bg-amber-100 text-amber-600">
          <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M12 9v2m0 4h.01M4.93 4.93l14.14 14.14M12 5a7 7 0 00-7 7v5h14v-5a7 7 0 00-7-7z" />
          </svg>
        </div>
        <div>
          <h1 class="text-base font-semibold text-slate-900">Je offerte wordt handmatig gecontroleerd</h1>
          <p class="mt-1 text-xs text-slate-500">
            We hebben je aanvraag ontvangen. Door de staat van de wanden is een korte handmatige review nodig
            voordat we een definitieve prijs kunnen tonen.
          </p>
        </div>
      </div>
      <div class="mt-4 rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-800">
        In de meeste gevallen ontvang je binnen korte tijd een bijgewerkte offerte per e-mail.
      </div>
    </div>
  </div>
</body>
</html>
                """,
                status_code=200,
            )
    except Exception:
        # Failsafe: als de review-check faalt, val terug op normale render-flow.
        pass

    html_key = (getattr(lead, "estimate_html_key", None) or "").strip()
    if not html_key:
        raise HTTPException(status_code=404, detail="Estimate not found")

    mark_lead_viewed(db, lead)
    db.commit()

    # Normaliseer tenant_id + key op dezelfde manier als de interne HTML-flow:
    # - tenant_id fallback naar "default"
    # - strip eventuele tenant-prefix uit html_key
    tenant_id = str((lead.tenant_id or "").strip() or "default")
    key = html_key
    prefix = f"{tenant_id}/"
    if key.startswith(prefix):
        key = key[len(prefix) :]

    logger.info(
        "PUBLIC_ESTIMATE_ROUTE lead_id=%s html_key_raw=%r key_norm=%r",
        getattr(lead, "id", None),
        html_key,
        key,
    )

    storage = get_storage()

    # ================
    # HTML laden
    # ================
    html = None
    iframe_url = None

    # Gedetailleerde debug-logging vóór het laden
    logger.info(
        "PUBLIC_ESTIMATE_LOAD_ATTEMPT lead_id=%s tenant_raw=%r tenant_norm=%s "
        "html_key_raw=%r key_norm=%r storage=%s",
        getattr(lead, "id", None),
        getattr(lead, "tenant_id", None),
        tenant_id,
        html_key,
        key,
        type(storage).__name__,
    )

    if isinstance(storage, LocalStorage):
        # LocalStorage: gebruik dezelfde publieke URL-strategie als de interne flow
        # (public_url) in plaats van download/get_text, om local_not_found issues te vermijden.
        try:
            iframe_url = storage.public_url(tenant_id=tenant_id, key=key)
        except Exception as e:
            logger.exception(
                "PUBLIC_ESTIMATE_LOCAL_URL_FAILED lead_id=%s tenant=%s key=%s exc=%r",
                getattr(lead, "id", None),
                tenant_id,
                key,
                e,
            )
            return HTMLResponse(
                content=f"""
<div style="max-width:900px;margin:40px auto;font-family:system-ui;">
  <h2>Estimate temporarily unavailable</h2>
  <p class="muted">We couldn't build a public URL for this estimate file.</p>
  <pre style="background:#f6f6f6;padding:12px;border-radius:10px;overflow:auto;">{html_key}</pre>
  <p>Please contact the contractor and ask them to resend the estimate.</p>
</div>
""",
                status_code=200,
            )
    else:
        try:
            html = get_text(storage, tenant_id=tenant_id, key=key)
        except Exception as e:
            # Log de exacte exception + traceback met alle relevante context
            logger.exception(
                "PUBLIC_ESTIMATE_LOAD_FAILED lead_id=%s tenant_raw=%r tenant_norm=%s "
                "html_key_raw=%r key_norm=%r storage=%s exc=%r",
                getattr(lead, "id", None),
                getattr(lead, "tenant_id", None),
                tenant_id,
                html_key,
                key,
                type(storage).__name__,
                e,
            )
            return HTMLResponse(
                content=f"""
<div style="max-width:900px;margin:40px auto;font-family:system-ui;">
  <h2>Estimate temporarily unavailable</h2>
  <p class="muted">We couldn't load this estimate file.</p>
  <pre style="background:#f6f6f6;padding:12px;border-radius:10px;overflow:auto;">{html_key}</pre>
  <p>Please contact the contractor and ask them to resend the estimate.</p>
</div>
""",
                status_code=200,
            )

    lead_status = (lead.status or "").upper()
    # Concept vs verstuurd:
    # - concept: offerte mag bekeken worden, maar nog niet geaccepteerd
    # - verstuurd: offerte is naar klant verstuurd → accept-knop toegestaan
    is_sent = lead_status in {"SENT", "VIEWED"} or bool(getattr(lead, "sent_at", None))
    show_accept = is_sent and lead_status not in {
        "ACCEPTED",
        "REJECTED",
        "DECLINED",
        "COMPLETED",
        "CANCELLED",
        "DONE",
    }

    # Bodycontent: inline HTML (S3) of iframe (LocalStorage)
    if iframe_url:
        body_html = f"""
<iframe src="{iframe_url}" style="width:100%;min-height:100vh;border:0;display:block;" loading="lazy"></iframe>
"""
    else:
        body_html = html

    page_html = paintly_templates.env.get_template("public/quote_page.html").render(
        token=lead.public_token,
        show_accept=show_accept,
        lead_status=lead_status,
        iframe_url=iframe_url,
        body_html=body_html or "",
    )
    return HTMLResponse(content=page_html)


@router_q.get("/{token}", response_class=HTMLResponse)
def public_quote_alias(token: str):
    """
    MVP-public route for customers: /q/{public_token}
    Keeps implementation DRY by delegating to existing /e/{token} handler.
    """
    # Use a 302 redirect so bookmarks continue to work even if /e implementation evolves.
    return RedirectResponse(url=f"/e/{token}", status_code=302)


@router.post("/{token}/accept")
def public_accept(
    token: str,
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    lead = db.query(Lead).filter(Lead.public_token == token).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Not found")

    if (lead.status or "").upper() != "ACCEPTED":
        mark_lead_accepted(db, lead)
        lead.reject_reason = None
        apply_workflow(db, lead)
        db.commit()

        override_email = (
            getattr(settings, "PAINTER_NOTIFICATION_OVERRIDE_EMAIL", "") or ""
        ).strip()

        try:
            painter = (
                db.query(User)
                .filter(User.tenant_id == lead.tenant_id)
                .filter(User.email.isnot(None))
                .filter(User.email != "")
                .order_by(User.id.asc())
                .first()
            )
            db_painter_email = (getattr(painter, "email", "") or "").strip()
        except Exception:
            db_painter_email = ""

        painter_email = override_email or db_painter_email

        if painter_email:
            base = (
                settings.APP_PUBLIC_BASE_URL
                or str(getattr(settings, "APP_PUBLIC_BASE_URL", ""))
                or ""
            ).rstrip("/")

            if not base:
                quote_url = f"/e/{lead.public_token}"
                admin_url = f"/app/leads/{lead.id}"
            else:
                quote_url = f"{base}/e/{lead.public_token}"
                admin_url = f"{base}/app/leads/{lead.id}"
            project_description, square_meters, job_type, price_display = (
                _extract_quote_summary(lead)
            )

            background.add_task(
                send_painter_accept_email,
                painter_email=painter_email,
                company_name="Paintly",
                lead_name=getattr(lead, "name", "") or "—",
                lead_email=getattr(lead, "email", "") or "",
                lead_phone=getattr(lead, "phone", "") or "",
                project_description=project_description,
                square_meters=square_meters,
                job_type=job_type,
                price_display=price_display,
                quote_url=quote_url,
                admin_url=admin_url,
            )

        if getattr(settings, "SEND_ACCEPT_CONFIRMATION_EMAIL", True):
            to_email = (getattr(lead, "email", "") or "").strip()
            if to_email:
                base = (settings.APP_PUBLIC_BASE_URL or "").rstrip("/")
                public_url = (
                    f"{base}/e/{lead.public_token}"
                    if base
                    else f"/e/{lead.public_token}"
                )
                customer_name = getattr(lead, "name", "") or ""
                company_name = "Paintly"

                async def _send():
                    html_body = render_estimate_accepted_email(
                        customer_name=customer_name,
                        quote_url=public_url,
                        company_name=company_name,
                    )
                    text_body = (
                        f"Beste {customer_name or 'klant'},\n\n"
                        "Bedankt, uw akkoord op de offerte is ontvangen.\n"
                        "We nemen binnenkort contact met u op om de planning te bevestigen.\n\n"
                        f"Bekijk uw offerte: {public_url}\n"
                    )
                    try:
                        await send_email(
                            to=to_email,
                            subject="Uw akkoord is ontvangen",
                            html_body=html_body,
                            text_body=text_body,
                            tag="customer-accepted",
                            metadata={
                                "lead_id": str(lead.id),
                                "tenant_id": str(lead.tenant_id),
                            },
                        )
                    except EmailSendError:
                        return

                background.add_task(_send)

    redirect_url = f"/e/{token}/accepted"

    if (request.headers.get("hx-request") or "").lower() == "true":
        return HTMLResponse("", headers={"HX-Redirect": redirect_url})

    accept = (request.headers.get("accept") or "").lower()
    if "application/json" in accept:
        return JSONResponse({"ok": True, "redirect": redirect_url})

    return RedirectResponse(url=redirect_url, status_code=303)


@router.post("/{token}/reject")
def public_reject(
    token: str,
    request: Request,
    reject_reason: str | None = Form(default=None),
    db: Session = Depends(get_db),
):
    lead = db.query(Lead).filter(Lead.public_token == token).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Not found")
    if (lead.status or "").upper() == "ACCEPTED":
        redirect_url = f"/e/{token}/accepted"
        if (request.headers.get("hx-request") or "").lower() == "true":
            return HTMLResponse("", headers={"HX-Redirect": redirect_url})
        accept = (request.headers.get("accept") or "").lower()
        if "application/json" in accept:
            return JSONResponse({"ok": True, "redirect": redirect_url})
        return RedirectResponse(url=redirect_url, status_code=303)

    lead.status = "REJECTED"
    reason = (reject_reason or "").strip()
    lead.reject_reason = reason[:1000] if reason else None
    db.add(lead)
    db.commit()

    redirect_url = f"/e/{token}/rejected"
    if (request.headers.get("hx-request") or "").lower() == "true":
        return HTMLResponse("", headers={"HX-Redirect": redirect_url})
    accept = (request.headers.get("accept") or "").lower()
    if "application/json" in accept:
        return JSONResponse({"ok": True, "redirect": redirect_url})
    return RedirectResponse(url=redirect_url, status_code=303)


@router.get("/{token}/accepted", response_class=HTMLResponse)
def public_accepted_confirmation(token: str, request: Request, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.public_token == token).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Not found")
    return paintly_templates.TemplateResponse(
        "public/quote_accepted_confirmation.html",
        {
            "request": request,
            "token": token,
        },
    )


@router.get("/{token}/rejected", response_class=HTMLResponse)
def public_rejected_confirmation(token: str, request: Request, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.public_token == token).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Not found")
    return paintly_templates.TemplateResponse(
        "public/quote_rejected_confirmation.html",
        {
            "request": request,
            "token": token,
        },
    )
