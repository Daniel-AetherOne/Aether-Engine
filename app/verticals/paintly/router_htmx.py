# app/verticals/paintly/router_htmx.py
from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth.deps import require_user_html
from app.db import get_db
from app.models.job import Job
from app.models.lead import Lead
from app.models.user import User

from app.verticals.paintly.router_app import (
    _get_tenant_timezone,
    _utc_to_local_human,
    get_estimate_overrides,
    public_url_for,
)

logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory="app/verticals/paintly/templates")

router = APIRouter(
    prefix="/app",
    tags=["paintly_htmx"],
    dependencies=[Depends(require_user_html)],
)


def _require_tenant_match(tenant_id: str, user: User) -> None:
    if str(user.tenant_id) != tenant_id:
        raise HTTPException(status_code=404, detail="Not found")


def _quote_ui_for_lead(lead: Lead) -> dict[str, Any]:
    has_estimate_html = bool((getattr(lead, "estimate_html_key", None) or "").strip())
    has_estimate_json = bool((getattr(lead, "estimate_json", None) or "").strip())
    has_final_price = getattr(lead, "final_price", None) is not None
    has_quote_output = has_estimate_html or has_estimate_json or has_final_price
    raw_status = (getattr(lead, "status", "") or "").upper()

    if not has_quote_output:
        quote_status = "none"
    elif raw_status == "ACCEPTED":
        quote_status = "accepted"
    elif raw_status == "NEEDS_REVIEW":
        quote_status = "review"
    elif raw_status in {"SENT", "VIEWED"}:
        quote_status = "sent"
    else:
        quote_status = "generated"

    can_generate = not has_quote_output
    can_view = has_estimate_html
    can_send = (
        has_estimate_html
        and raw_status in {"SUCCEEDED", "SENT", "VIEWED", "REJECTED"}
        and bool((getattr(lead, "email", "") or "").strip())
    )
    can_edit = has_quote_output and raw_status != "ACCEPTED"
    can_regenerate = has_quote_output and raw_status != "ACCEPTED"

    return {
        "has_estimate": has_estimate_html,
        "has_quote_output": has_quote_output,
        "quote_status": quote_status,
        "can_generate": can_generate,
        "can_view": can_view,
        "can_edit": can_edit,
        "can_regenerate": can_regenerate,
        "can_send": can_send,
        "can_copy_link": False,
        "can_download_pdf": False,
        "public_quote_url": None,
    }


def timeline_rows_for_lead(lead: Lead, tz_name: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    rows.append(
        {
            "label": "Aangemaakt",
            "value": _utc_to_local_human(getattr(lead, "created_at", None), tz_name) or "—",
            "tone": "slate",
        }
    )
    if getattr(lead, "sent_at", None):
        rows.append(
            {
                "label": "Verstuurd naar klant",
                "value": _utc_to_local_human(lead.sent_at, tz_name),
                "tone": "sky",
            }
        )
    if getattr(lead, "viewed_at", None):
        rows.append(
            {
                "label": "Bekeken door klant",
                "value": _utc_to_local_human(lead.viewed_at, tz_name),
                "tone": "amber",
            }
        )
    st = (lead.status or "").upper()
    if st == "ACCEPTED" and getattr(lead, "accepted_at", None):
        rows.append(
            {
                "label": "Geaccepteerd",
                "value": _utc_to_local_human(lead.accepted_at, tz_name),
                "tone": "emerald",
            }
        )
    elif st == "REJECTED":
        rows.append(
            {
                "label": "Afgewezen",
                "value": _utc_to_local_human(getattr(lead, "updated_at", None), tz_name)
                or "—",
                "tone": "rose",
            }
        )
        if getattr(lead, "reject_reason", None):
            rows.append(
                {
                    "label": "Toelichting klant",
                    "value": (lead.reject_reason or "")[:500],
                    "tone": "rose",
                    "small": True,
                }
            )
    return rows


def build_quote_oob_context(
    request: Request,
    db: Session,
    current_user: User,
    lead: Lead,
) -> dict[str, Any]:
    job = (
        db.query(Job)
        .filter(Job.lead_id == lead.id, Job.tenant_id == str(current_user.tenant_id))
        .first()
    )
    tz_name = _get_tenant_timezone(current_user, job)
    quote_ui = _quote_ui_for_lead(lead)
    public_quote_url = public_url_for(request, lead)
    raw_status = (getattr(lead, "status", "") or "").upper()
    quote_ui["can_copy_link"] = bool(public_quote_url) and raw_status in {
        "SENT",
        "VIEWED",
        "REJECTED",
        "ACCEPTED",
    }
    quote_ui["can_download_pdf"] = bool(lead.estimate_html_key) and raw_status in {
        "SENT",
        "VIEWED",
        "REJECTED",
        "ACCEPTED",
    }
    quote_ui["public_quote_url"] = public_quote_url

    st = raw_status
    status_labels = {
        "ACCEPTED": "Geaccepteerd",
        "DONE": "Afgerond",
        "COMPLETED": "Compleet",
        "SENT": "Verstuurd",
        "VIEWED": "Bekeken",
        "REJECTED": "Afgewezen",
        "DECLINED": "Afgewezen",
        "CANCELLED": "Geannuleerd",
        "NEW": "Nieuw",
    }
    if st in ["ACCEPTED", "DONE", "COMPLETED"]:
        lead_status_badge = "bg-emerald-50 text-emerald-700"
    elif st in ["SENT", "VIEWED"]:
        lead_status_badge = "bg-amber-50 text-amber-700"
    elif st in ["REJECTED", "DECLINED", "CANCELLED"]:
        lead_status_badge = "bg-rose-50 text-rose-700"
    else:
        lead_status_badge = "bg-slate-100 text-slate-600"

    overrides = get_estimate_overrides(lead)
    internal_notes = str(overrides.get("internal_notes") or "")

    return {
        "request": request,
        "lead": lead,
        "job": job,
        "quote_ui": quote_ui,
        "tz_name": tz_name,
        "sent_display": _utc_to_local_human(getattr(lead, "sent_at", None), tz_name),
        "timeline_rows": timeline_rows_for_lead(lead, tz_name),
        "status_labels": status_labels,
        "lead_status_badge": lead_status_badge,
        "st": st,
        "internal_notes": internal_notes,
    }


def _render_template(name: str, ctx: dict[str, Any]) -> str:
    t = templates.env.get_template(name)
    return t.render(ctx)


def render_quote_oob_response(
    request: Request,
    db: Session,
    current_user: User,
    lead_id: str,
    *,
    toast_title: str = "Offerte verstuurd",
    toast_message: str = "De klant ontvangt de e-mail binnenkort.",
) -> HTMLResponse:
    lead = (
        db.query(Lead)
        .filter(Lead.id == lead_id, Lead.tenant_id == str(current_user.tenant_id))
        .first()
    )
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    ctx = build_quote_oob_context(request, db, current_user, lead)
    html = _render_template("quotes/partials/send_success_oob.html", ctx)
    trigger = json.dumps(
        {
            "show-toast": {
                "level": "success",
                "title": toast_title,
                "message": toast_message,
            }
        }
    )
    return HTMLResponse(content=html, headers={"HX-Trigger": trigger})


@router.get(
    "/tenants/{tenant_id}/quotes/{quote_id}/partials/summary",
    response_class=HTMLResponse,
)
def hx_quote_summary_oob(
    tenant_id: str,
    quote_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user_html),
):
    _require_tenant_match(tenant_id, current_user)
    lead = (
        db.query(Lead)
        .filter(Lead.id == quote_id, Lead.tenant_id == tenant_id)
        .first()
    )
    if not lead:
        raise HTTPException(status_code=404, detail="Not found")

    ctx = build_quote_oob_context(request, db, current_user, lead)
    html = _render_template("quotes/partials/send_success_oob.html", ctx)
    return HTMLResponse(content=html)


@router.post(
    "/tenants/{tenant_id}/quotes/{quote_id}/partials/internal-notes",
    response_class=HTMLResponse,
)
def hx_save_internal_notes(
    tenant_id: str,
    quote_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user_html),
    internal_notes: str = Form(""),
):
    _require_tenant_match(tenant_id, current_user)
    lead = (
        db.query(Lead)
        .filter(Lead.id == quote_id, Lead.tenant_id == tenant_id)
        .first()
    )
    if not lead:
        raise HTTPException(status_code=404, detail="Not found")

    overrides = get_estimate_overrides(lead)
    overrides["internal_notes"] = (internal_notes or "")[:8000]
    lead.estimate_overrides_json = json.dumps(overrides, ensure_ascii=False)
    db.add(lead)
    db.commit()
    db.refresh(lead)

    ctx = build_quote_oob_context(request, db, current_user, lead)
    notes_html = _render_template("quotes/partials/internal_notes.html", ctx)
    oob_html = _render_template("quotes/partials/send_success_oob.html", ctx)
    html = notes_html + oob_html
    trigger = json.dumps(
        {
            "show-toast": {
                "level": "success",
                "title": "Opgeslagen",
                "message": "Interne notities bijgewerkt.",
            }
        }
    )
    return HTMLResponse(
        content=html,
        headers={"HX-Trigger": trigger},
    )
