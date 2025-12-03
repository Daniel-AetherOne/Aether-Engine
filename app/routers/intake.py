# app/routers/intake.py

from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import logging

from app.db import get_db
from app.schemas.intake import IntakePayload
from app.models import Lead, LeadFile
from app.services.pricing_engine import calculate_quote

router = APIRouter(prefix="/intake", tags=["intake"])
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger(__name__)


# ----------------------------
# GET /intake/upload – intakepagina met formulier
# ----------------------------
@router.get("/upload", response_class=HTMLResponse)
def intake_upload(request: Request, lead_id: str = "test"):
    """
    Render het intake formulier (intake_form.html).
    """
    return templates.TemplateResponse(
        "intake_form.html",
        {
            "request": request,
            "lead_id": lead_id,
        },
    )


# ----------------------------
# POST /intake/lead – maak lead aan en koppel uploads
# ----------------------------
@router.post("/lead")
async def create_lead(request: Request, db: Session = Depends(get_db)):
    """
    Ontvangt multipart/form-data van intake_form.html:

    - tekstvelden: name, email, phone, square_meters, address
    - photo_keys: S3 keys vanuit frontend (hidden inputs)

    Zet dat om naar een IntakePayload, slaat de lead op en koppelt de
    S3-keys als LeadFile records. Daarna wordt automatisch een quote
    berekend via de pricing engine.
    """
    form = await request.form()
    form_dict = dict(form)

    # S3-keys uit hidden inputs
    photo_keys = form.getlist("photo_keys") if hasattr(form, "getlist") else []

    # Bouw payload zoals IntakePayload verwacht
    payload_data = {
        "tenant_id": form_dict.get("tenant_id"),
        "name": form_dict.get("name"),
        "email": form_dict.get("email"),
        "phone": form_dict.get("phone"),
        "project_description": form_dict.get("address"),
        "object_keys": photo_keys,
        "square_meters": float(form_dict.get("square_meters")) if form_dict.get("square_meters") else None,
    }


    try:
        payload = IntakePayload(**payload_data)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid intake payload: {e}",
        )

    tenant_id = payload.tenant_id or "default"

    # Log ter debuggen
    try:
        logger.info("INTAKE payload: %s", payload.model_dump())
    except Exception:
        logger.info("INTAKE payload ontvangen (logging model_dump faalde)")

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

        # 2) Uploads opslaan (eenvoudige variant: geen head_ok / finalize_move)
        saved_keys: list[str] = []
        object_keys = list(dict.fromkeys(payload.object_keys or []))  # dedupe, volgorde behouden

        for key in object_keys:
            # We gaan er vanuit dat deze key al correct in S3 staat
            db.add(
                LeadFile(
                    lead_id=lead.id,
                    s3_key=key,
                    size_bytes=0,           # kan later met head_ok worden ingevuld
                    content_type="image/*", # idem, later verfijnen
                )
            )
            saved_keys.append(key)

        db.commit()

        # 3) Price engine aanroepen → Quote object
        quote = calculate_quote(payload, lead)

        return {
            "lead_id": lead.id,
            "files": saved_keys,
            "quote": quote,
        }

    except HTTPException:
        # al nette fout → doorgeven
        raise
    except Exception as e:
        logger.exception("create_lead crashed")
        raise HTTPException(status_code=500, detail=str(e))
