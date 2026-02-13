from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.db import get_db
from app.models.lead import Lead
from app.models.job import Job
from app.services.storage import get_storage, get_text

router = APIRouter(prefix="/e", tags=["public_estimate"])


@router.get("/{token}", response_class=HTMLResponse)
def public_estimate(token: str, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.public_token == token).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Not found")

    html_key = lead.estimate_html_key
    if not html_key:
        raise HTTPException(status_code=404, detail="Estimate not found")

    # mark viewed (alleen 1x)
    if not getattr(lead, "viewed_at", None):
        lead.viewed_at = datetime.now(timezone.utc)
        if (lead.status or "").upper() == "SENT":
            lead.status = "VIEWED"
        db.add(lead)
        db.commit()

    storage = get_storage()
    html = get_text(storage, tenant_id=str(lead.tenant_id), key=html_key)
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


@router.post("/{token}/accept")
def public_accept(token: str, db: Session = Depends(get_db)):
    print(">>> PUBLIC_ACCEPT HIT", token)

    lead = db.query(Lead).filter(Lead.public_token == token).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Not found")

    lead.status = "ACCEPTED"
    lead.accepted_at = datetime.now(timezone.utc)
    db.add(lead)

    existing = db.query(Job).filter(Job.lead_id == lead.id).first()
    if not existing:
        db.add(Job(tenant_id=str(lead.tenant_id), lead_id=lead.id, status="NEW"))

    db.flush()
    print(
        ">>> JOB EXISTS AFTER FLUSH",
        db.query(Job).filter(Job.lead_id == lead.id).first(),
    )

    db.commit()
    return RedirectResponse(url=f"/e/{token}", status_code=303)
