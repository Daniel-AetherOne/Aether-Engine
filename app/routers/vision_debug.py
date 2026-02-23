# app/routers/vision_debug.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.verticals.registry import get as get_vertical

router = APIRouter(prefix="/vision", tags=["vision"])


@router.post("/run/{lead_id}")
def run_vision(lead_id: int, db: Session = Depends(get_db)):
    try:
        # Single-vertical for now, but registry-based
        v = get_vertical("paintly")
        vision_output = v.run_vision(db, lead_id)

        return {
            "lead_id": lead_id,
            "vertical": v.vertical_id,
            "vision_output": vision_output,
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
