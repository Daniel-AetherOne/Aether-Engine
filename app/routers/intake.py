# app/routers/intake.py
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import logging

from app.db import get_db
from app.schemas.intake import IntakePayload
from app.models import Lead, LeadFile
from app.services.storage import get_storage, head_ok, finalize_move

router = APIRouter(prefix="/intake", tags=["intake"])
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger(__name__)


# ----------------------------
# GET /intake/upload – uploadpagina
# ----------------------------
@router.get("/upload", response_class=HTMLResponse)
def intake_upload(request: Request, lead_id: str = "test"):
    return templates.TemplateResponse(
        "intake_upload.html",
        {"request": request, "lead_id": lead_id},
    )


# ----------------------------
# POST /intake/lead – maak lead aan en koppel uploads
# ----------------------------
@router.post("/lead")
def create_lead(payload: IntakePayload, db: Session = Depends(get_db)):
    storage = get_storage()
    tenant_id = payload.tenant_id or "default"

    # Log ter debuggen
    try:
        logger.info("INTAKE payload: %s", payload.model_dump())
    except Exception:
        logger.info("INTAKE payload ontvangen")

    try:
        # 1) Lead aanmaken
        lead = Lead(
            tenant_id=tenant_id,
            name=payload.name,
            email=payload.email,
            phone=payload.phone,
            # oude veldnaam gemapt naar notes
            notes=payload.project_description,
        )
        db.add(lead)
        db.commit()
        db.refresh(lead)

        # 2) Uploads verifiëren & verplaatsen
        saved_keys = []
        object_keys = list(dict.fromkeys(payload.object_keys or []))  # dedupe, behoud volgorde

        for key in object_keys:
            # Verifieer tijdelijke key (tenant-loos, begint met uploads/..)
            ok, meta, err = head_ok(storage, tenant_id, key)
            if not ok:
                logger.warning("head_ok FAILED: key=%s err=%s meta=%s", key, err, meta)
                raise HTTPException(status_code=400, detail={"key": key, "error": err})

            # Haal grootte en content-type uit meta (werkt voor S3 én local)
            size = (
                meta.get("ContentLength")
                or meta.get("size")
                or meta.get("Size")
                or 0
            )
            try:
                size = int(size)
            except Exception:
                size = 0

            content_type = (
                meta.get("ContentType")
                or meta.get("content_type")
                or "application/octet-stream"
            )

            # Verplaats naar definitieve locatie: leads/{lead_id}/filename
            try:
                final_key = finalize_move(storage, tenant_id, key, str(lead.id))
            except Exception as move_err:
                logger.exception("finalize_move failed for key=%s", key)
                raise HTTPException(
                    status_code=500,
                    detail={"key": key, "error": f"finalize_move_failed: {move_err}"},
                )

            # Sla koppeling op met verplichte kolommen
            db.add(
                LeadFile(
                    lead_id=lead.id,
                    s3_key=final_key,
                    size_bytes=size,
                    content_type=content_type,
                )
            )
            saved_keys.append(final_key)

        db.commit()

        return {"lead_id": lead.id, "files": saved_keys}

    except HTTPException:
        # al nette fout → doorgeven
        raise
    except Exception as e:
        logger.exception("create_lead crashed")
        # geef detail terug zodat je in de UI ziet wat er mis is
        raise HTTPException(status_code=500, detail=str(e))
