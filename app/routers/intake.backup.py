# app/routers/intake.py
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/intake", tags=["intake"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/upload", response_class=HTMLResponse)
def intake_upload(request: Request, lead_id: str):
    return templates.TemplateResponse(
        "intake_upload.html",
        {"request": request, "lead_id": lead_id},
    )

# >>> Laat ALLE andere (interne) imports voorlopig weg <<<
# from app.models.lead import Lead
# from app.models.intake import IntakeResponse
# from app.models.tenant_settings import TenantSettings
# from app.services.intake_service import IntakeService
# from app.services.lead_store import lead_store
# from app.services.s3 import S3Service
# from app.utils.tenants import get_tenant, get_tenant_settings


# ---------------------------------------------------
# Router setup
# ---------------------------------------------------

router = APIRouter(prefix="/intake", tags=["intake"])
templates = Jinja2Templates(directory="app/templates")
intake_service = IntakeService()

# ---------------------------------------------------
# Upload page (new)
# ---------------------------------------------------

@router.get("/upload", response_class=HTMLResponse)
def intake_upload(request: Request, lead_id: str):
    """
    Render de eenvoudige uploadpagina voor een lead.
    """
    return templates.TemplateResponse(
        "intake_upload.html",
        {"request": request, "lead_id": lead_id},
    )

# ---------------------------------------------------
# (andere bestaande intake-routes volgen hieronder)
# ---------------------------------------------------

# -----------------------------
# HTML intake formulier
# -----------------------------
@router.get("/form", response_class=HTMLResponse)
async def get_intake_form(
    request: Request,
    tenant_id: str = Depends(resolve_tenant),
    tenant_settings: TenantSettings = Depends(get_tenant_settings),
):
    """Render intake form met tenant-specifieke branding."""
    return templates.TemplateResponse(
        "intake_form.html",
        {
            "request": request,
            "tenant_id": tenant_id,
            "tenant": {
                "company_name": tenant_settings.company_name,
                "logo_url": tenant_settings.logo_url,
                "primary_color": tenant_settings.primary_color,
                "secondary_color": tenant_settings.secondary_color,
            },
        },
    )


# -----------------------------
# Intake submit (upload + lead)
# -----------------------------
@router.post("", response_model=IntakeResponse)
async def submit_intake(
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(""),
    address: str = Form(""),
    square_meters: float = Form(...),
    images: List[UploadFile] = File(default=[]),
    tenant_id: str = Depends(resolve_tenant),
    tenant_settings: TenantSettings = Depends(get_tenant_settings),
):
    """Submit intake met tenant-aware opslag (S3)."""
    if square_meters <= 0:
        raise HTTPException(status_code=400, detail="square_meters must be > 0")

    # 1) Lead ID genereren
    lead_id = intake_service.generate_lead_id()

    # 2) Bestanden opslaan -> lijst van S3 keys (strings)
    saved_files = await intake_service.save_files(images or [], lead_id, tenant_id)

    # 3) Lead persistent opslaan met S3-keys
    lead = Lead(
        lead_id=lead_id,
        tenant_id=tenant_id,
        name=name,
        email=email,
        phone=phone,
        address=address,
        square_meters=square_meters,
        uploaded_files=saved_files,
        submission_date=datetime.utcnow(),
        status="submitted",
        notes=None,
    )
    LeadStore.upsert(lead)

    # 4) Logging
    intake_service.logger.info(
        f"[TENANT:{tenant_id}] Intake submitted for {name} ({email}) - {len(saved_files)} files uploaded"
    )

    # 5) Response (zoals je al had)
    return IntakeResponse(
        lead_id=lead_id,
        tenant_id=tenant_id,
        name=name,
        email=email,
        phone=phone,
        address=address,
        square_meters=square_meters,
        uploaded_files=saved_files,
        submission_date=datetime.utcnow(),
        status="submitted",
    )


# -----------------------------
# Stats per tenant (placeholder)
# -----------------------------
@router.get("/stats/{tenant_id}")
async def get_tenant_stats(
    tenant_id: str,
    current_tenant_id: str = Depends(resolve_tenant),
):
    """Upload-statistieken voor specifieke tenant (autorisatie check)."""
    if tenant_id != current_tenant_id:
        raise HTTPException(
            status_code=403,
            detail="You can only access statistics for your own tenant",
        )
    stats = intake_service.get_tenant_upload_stats(tenant_id)
    return {"tenant_id": tenant_id, "statistics": stats}


# -----------------------------
# Leads (lijst) – placeholder
# -----------------------------
@router.get("/leads")
async def list_tenant_leads(
    tenant_id: str = Depends(resolve_tenant),
    tenant_settings: TenantSettings = Depends(get_tenant_settings),
):
    """Placeholder: later DB-koppeling; nu enkel metadata terug."""
    return {
        "tenant_id": tenant_id,
        "company_name": tenant_settings.company_name,
        "leads": [],
        "message": "Lead listing not yet implemented - would connect to database",
    }


# -----------------------------
# Lead detail ophalen
# -----------------------------
@router.get("/lead/{lead_id}")
async def get_lead_detail(lead_id: str):
    lead = LeadStore.get(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return {"ok": True, "lead": lead}


# -----------------------------
# Presigned download-URLs
# -----------------------------
class PresignedFile(BaseModel):
    key: str
    url: str


@router.get("/lead/{lead_id}/files")
async def get_lead_files(lead_id: str, expires: int = 900):
    """Geef voor alle geüploade bestanden tijdelijke download-URLs."""
    lead = LeadStore.get(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    s3 = S3Service()
    files = [
        PresignedFile(key=k, url=s3.presigned_get(k, expires_in=expires))
        for k in (lead.uploaded_files or [])
    ]
    return {"ok": True, "files": [f.model_dump() for f in files]}
