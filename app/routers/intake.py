# app/routers/intake.py

from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
import logging

from app.db import get_db
from app.verticals.registry import get as get_vertical

router = APIRouter(prefix="/intake", tags=["intake"])
logger = logging.getLogger(__name__)

VERTICAL = "painters_us"  # single-vertical for now (still via registry)


@router.get("/painters-us", response_class=HTMLResponse)
def intake_painters_us(request: Request, lead_id: str = "test"):
    v = get_vertical(VERTICAL)
    return v.render_intake_form(request, lead_id=lead_id)


@router.post("/lead")
async def create_lead(request: Request, db: Session = Depends(get_db)):
    v = get_vertical(VERTICAL)

    try:
        result = await v.create_lead_from_form(request, db)
        logger.info(
            "INTAKE created lead=%s vertical=%s", result.lead_id, result.vertical
        )

        return {
            "lead_id": result.lead_id,
            "tenant_id": result.tenant_id,
            "files": result.files,
            "vertical": result.vertical,
            "next": {
                "vision": f"/vision/run/{result.lead_id}",
                "publish_estimate": f"/quotes/publish/{result.lead_id}",
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("create_lead crashed")
        raise HTTPException(status_code=500, detail=str(e))
