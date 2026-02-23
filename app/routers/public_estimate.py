# app/routers/public_estimate.py
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.db import get_db
from app.models.lead import Lead
from app.services.email import EmailError, send_postmark_email
from app.services.storage import get_storage, get_text
from app.verticals.paintly.email_render import render_estimate_accepted_email
from app.workflow.status import apply_workflow

from app.services.workflow import (
    mark_lead_viewed,
    mark_lead_accepted,
    ensure_job_for_lead,
)

router = APIRouter(prefix="/e", tags=["public_estimate"])


@router.get("/{token}", response_class=HTMLResponse)
def public_estimate(token: str, request: Request, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.public_token == token).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Not found")

    html_key = getattr(lead, "estimate_html_key", None)
    if not html_key:
        raise HTTPException(status_code=404, detail="Estimate not found")

    # mark viewed (alleen 1x) + status SENT -> VIEWED
    mark_lead_viewed(db, lead)
    db.commit()

    storage = get_storage()

    try:
        html = get_text(storage, tenant_id=str(lead.tenant_id), key=html_key)
    except Exception:
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
    show_accept = lead_status not in {"ACCEPTED", "COMPLETED", "CANCELLED", "DONE"}

    accepted_param = (request.query_params.get("accepted") or "").strip() == "1"
    show_accepted_banner = (lead_status == "ACCEPTED") or accepted_param

    accepted_banner = ""
    if show_accepted_banner and not show_accept:
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

    if show_accept:
        # NOTE: NOT an f-string. We use .format(token=...) and escape JS braces as {{ }}
        accept_bar = """
<!-- Tailwind CDN (safe to include; estimate.html already has it, but this makes bar work even if estimate HTML changes) -->
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
      <div class="rounded-2xl border px-4 py-3 text-sm ${
        type==='success'
          ? 'border-emerald-200 bg-emerald-50 text-emerald-950'
          : 'border-rose-200 bg-rose-50 text-rose-950'
      }">
        <div class="font-semibold">${{type==='success' ? 'Accepted' : 'Could not accept'}}</div>
        <div class="mt-1 text-sm opacity-90">${{msg}}</div>
      </div>
    `;
  }}

  form.addEventListener('submit', async (e) => {{
    // progressive enhancement (works without JS too)
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

      show('success', 'Redirecting…');
      setTimeout(() => {{ window.location.href = '/e/{token}?accepted=1'; }}, 450);
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

        return HTMLResponse(content=accept_bar + html)

    return HTMLResponse(content=accepted_banner + html)


@router.post("/{token}/accept")
def public_accept(
    token: str, background: BackgroundTasks, db: Session = Depends(get_db)
):
    lead = db.query(Lead).filter(Lead.public_token == token).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Not found")

    # only do work once
    if (lead.status or "").upper() != "ACCEPTED":
        mark_lead_accepted(db, lead)
        ensure_job_for_lead(db, lead)
        apply_workflow(db, lead)
        db.commit()

        # optional: send confirmation email (best-effort)
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

                def _send():
                    html_body = render_estimate_accepted_email(
                        customer_name=customer_name,
                        public_url=public_url,
                        company_name=company_name,
                    )
                    try:
                        send_postmark_email(
                            to=to_email,
                            subject="We received your acceptance",
                            html_body=html_body,
                            metadata={
                                "lead_id": str(lead.id),
                                "tenant_id": str(lead.tenant_id),
                            },
                        )
                    except EmailError:
                        return

                background.add_task(_send)

    return RedirectResponse(url=f"/e/{token}?accepted=1", status_code=303)
