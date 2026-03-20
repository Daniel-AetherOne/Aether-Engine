# app/routers/public_estimate.py
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
import logging

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
from app.verticals.paintly.email_render import render_estimate_accepted_email
from app.workflow.status import apply_workflow

router = APIRouter(prefix="/e", tags=["public_estimate"])
# Alias router for simple customer-friendly quote URL (/q/{public_token})
router_q = APIRouter(prefix="/q", tags=["public_quote"])

logger = logging.getLogger(__name__)


async def send_painter_accept_email(
    *,
    painter_email: str,
    lead_id: str,
    lead_name: str,
    lead_email: str,
    quote_url: str,
    admin_url: str,
) -> None:
    subject = f"Offerte geaccepteerd - {lead_name}"

    html_body = f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #111;">
        <h2>Offerte geaccepteerd</h2>
        <p>Een klant heeft de offerte geaccepteerd.</p>

        <ul>
          <li><strong>Klant:</strong> {lead_name}</li>
          <li><strong>Email:</strong> {lead_email}</li>
          <li><strong>Lead ID:</strong> {lead_id}</li>
        </ul>

        <p>
          <a href="{admin_url}" style="display:inline-block;padding:12px 18px;background:#111;color:#fff;text-decoration:none;border-radius:8px;">
            Open dashboard
          </a>
        </p>

        <p>
          Offerte bekijken:<br>
          <a href="{quote_url}">{quote_url}</a>
        </p>
      </body>
    </html>
    """

    text_body = (
        "Offerte geaccepteerd.\n\n"
        f"Klant: {lead_name}\n"
        f"Email: {lead_email}\n"
        f"Lead ID: {lead_id}\n\n"
        f"Dashboard: {admin_url}\n"
        f"Offerte: {quote_url}\n"
    )

    await send_email(
        to=painter_email,
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        tag="painter-accepted",
        metadata={"lead_id": str(lead_id)},
    )


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
    show_accept = is_sent and lead_status not in {"ACCEPTED", "COMPLETED", "CANCELLED", "DONE"}

    accepted_param = (request.query_params.get("accepted") or "").strip() == "1"
    show_accepted_banner = (lead_status == "ACCEPTED") or accepted_param

    accepted_banner = ""
    if show_accepted_banner:
        accepted_banner = """
<div class="no-print sticky top-0 z-[9999] border-b border-emerald-200 bg-emerald-50">
  <div class="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-3">
    <div class="flex items-center gap-2">
      <span class="inline-flex h-8 w-8 items-center justify-center rounded-xl bg-emerald-600 text-white font-black">✓</span>
      <div>
        <div class="text-sm font-semibold text-emerald-950">Accepted — thank you!</div>
        <div class="text-xs text-emerald-900/80">We’ll contact you shortly to confirm details.</div>
      </div>
    </div>
    <a href="#" onclick="window.print(); return false;"
       class="hidden sm:inline-flex items-center rounded-xl bg-white px-3 py-2 text-xs font-semibold text-emerald-900 shadow-sm ring-1 ring-inset ring-emerald-200 hover:bg-emerald-50">
      Print
    </a>
  </div>
</div>
"""

    # Bodycontent: inline HTML (S3) of iframe (LocalStorage)
    if iframe_url:
        body_html = f"""
<iframe src="{iframe_url}" style="width:100%;min-height:100vh;border:0;display:block;" loading="lazy"></iframe>
"""
    else:
        body_html = html

    if show_accept:
        accept_bar = """
<script src="https://cdn.tailwindcss.com"></script>

<div class="no-print sticky top-0 z-[9999] border-b border-slate-200 bg-white/90 backdrop-blur">
  <div class="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-3">
    <div class="flex items-center gap-3">
      <div class="h-9 w-9 rounded-2xl bg-slate-900 text-white grid place-items-center font-black tracking-tight">P</div>
      <div>
        <div class="text-sm font-semibold text-slate-900">Your estimate is ready</div>
        <div class="text-xs text-slate-600">Review the details below and accept when you’re ready.</div>
      </div>
    </div>

    <div class="flex items-center gap-2">
      <form id="acceptForm" method="post" action="/e/{token}/accept" class="m-0">
        <button
          id="acceptBtn"
          type="submit"
          class="inline-flex items-center rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
        >
          Accept estimate
        </button>
      </form>

      <a href="#" onclick="window.scrollTo({{ top: document.body.scrollHeight, behavior: 'smooth' }}); return false;"
         class="hidden sm:inline-flex items-center rounded-xl bg-white px-4 py-2 text-sm font-semibold text-slate-900 shadow-sm ring-1 ring-inset ring-slate-200 hover:bg-slate-50">
        See summary
      </a>
    </div>
  </div>

  <div id="acceptFlash" class="mx-auto hidden max-w-6xl px-4 pb-3"></div>
</div>

<script>
(function(){{
  const form = document.getElementById('acceptForm');
  const btn = document.getElementById('acceptBtn');
  const flashWrap = document.getElementById('acceptFlash');
  if(!form || !btn || !flashWrap) return;

   function show(type, msg){{
    flashWrap.classList.remove('hidden');
    flashWrap.innerHTML = `
      <div class="rounded-2xl border px-4 py-3 text-sm ${{
        type==='success'
          ? 'border-emerald-200 bg-emerald-50 text-emerald-950'
          : 'border-rose-200 bg-rose-50 text-rose-950'
      }}">
        <div class="font-semibold">${{type==='success' ? 'Accepted' : 'Could not accept'}}</div>
        <div class="mt-1 text-sm opacity-90">${{msg}}</div>
      </div>
    `;
  }}

  form.addEventListener('submit', async (e) => {{
    e.preventDefault();
    btn.disabled = true;
    const old = btn.textContent;
    btn.textContent = 'Accepting…';

    try {{
      const res = await fetch(form.action, {{
        method: 'POST',
        headers: {{ 'Accept': 'application/json' }}
      }});

      if (!res.ok) {{
        let data = {{}};
        try {{ data = await res.json(); }} catch(_) {{}}
        throw new Error((data && (data.detail || data.error)) || 'Failed to accept');
      }}

      let data = {{}};
      try {{ data = await res.json(); }} catch(_) {{}}
      show('success', 'Redirecting…');
      setTimeout(() => {{
        window.location.href = (data && data.redirect) ? data.redirect : '/e/{token}?accepted=1';
      }}, 350);
    }} catch (err) {{
      show('error', err && err.message ? err.message : 'Something went wrong');
      btn.disabled = false;
      btn.textContent = old;
    }}
  }});
}})();
</script>
""".format(
            token=lead.public_token
        )

        return HTMLResponse(content=accept_bar + body_html)

    return HTMLResponse(content=accepted_banner + body_html)


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

            background.add_task(
                send_painter_accept_email,
                painter_email=painter_email,
                lead_id=lead.id,
                lead_name=getattr(lead, "name", "") or "—",
                lead_email=getattr(lead, "email", "") or "",
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
                        f"Hi {customer_name},\n\n"
                        "We received your acceptance.\n\n"
                        f"View your estimate: {public_url}\n"
                    )
                    try:
                        await send_email(
                            to=to_email,
                            subject="We received your acceptance",
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

    redirect_url = f"/e/{token}?accepted=1"

    accept = (request.headers.get("accept") or "").lower()
    if "application/json" in accept:
        return JSONResponse({"ok": True, "redirect": redirect_url})

    return RedirectResponse(url=redirect_url, status_code=303)
