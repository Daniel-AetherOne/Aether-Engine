from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Lead
from app.verticals.paintly.pipeline import compute_quote_for_lead

router = APIRouter(prefix="/quote", tags=["quote"])


@router.post("/run/{lead_id}")
def run_quote(lead_id: str, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    out = compute_quote_for_lead(db, lead, render_html=False)
    return out  # bevat estimate_json
