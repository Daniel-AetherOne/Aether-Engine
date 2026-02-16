# app/routers/public_estimate.py
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.workflow.status import apply_workflow

from app.db import get_db
from app.models.lead import Lead
from app.services.storage import get_storage, get_text

from app.services.workflow import (
    mark_lead_viewed,
    mark_lead_accepted,
    ensure_job_for_lead,
)

router = APIRouter(prefix="/e", tags=["public_estimate"])


@router.get("/{token}", response_class=HTMLResponse)
def public_estimate(token: str, db: Session = Depends(get_db)):
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
    html = get_text(storage, tenant_id=str(lead.tenant_id), key=html_key)

    # Accept-bar alleen als nog niet geaccepteerd/afgerond/geannuleerd
    lead_status = (lead.status or "").upper()
    show_accept = lead_status not in {"ACCEPTED", "COMPLETED", "CANCELLED"}

    if show_accept:
        accept_bar = f"""
<div style="position:sticky;top:0;background:#111827;color:white;padding:12px;z-index:9999">
  <div style="max-width:1000px;margin:0 auto;display:flex;justify-content:space-between;align-items:center">
    <div>Estimate from Paintly</div>
    <form method="post" action="/e/{lead.public_token}/accept" style="margin:0">
      <button style="padding:8px 12px;border-radius:10px;border:0;cursor:pointer">
        Accept estimate
      </button>
    </form>
  </div>
</div>
"""
        return HTMLResponse(content=accept_bar + html)

    return HTMLResponse(content=html)


@router.post("/{token}/accept")
def public_accept(token: str, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.public_token == token).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Not found")

    lead.status = "ACCEPTED"
    lead.accepted_at = datetime.now(timezone.utc)
    db.add(lead)

    # automatisch job etc.
    apply_workflow(db, lead)

    db.commit()
    return RedirectResponse(url=f"/e/{token}", status_code=303)
