# app/routers/intake.py
from fastapi import APIRouter, Form, UploadFile, File, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from datetime import datetime
import uuid, shutil

from app.models.intake import IntakeResponse
from app.dependencies import resolve_tenant, get_tenant_settings
from app.services.intake_service import IntakeService
from app.models.tenant import TenantSettings

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
intake_service = IntakeService()

# GET /intake/form → HTML formulier met tenant branding
@router.get("/form", response_class=HTMLResponse)
async def get_intake_form(
    request: Request,
    tenant_id: str = Depends(resolve_tenant),
    tenant_settings: TenantSettings = Depends(get_tenant_settings)
):
    """Render intake form met tenant-specifieke branding"""
    return templates.TemplateResponse("intake_form.html", {
        "request": request,
        "tenant_id": tenant_id,
        "tenant": {
            "company_name": tenant_settings.company_name,
            "logo_url": tenant_settings.logo_url,
            "primary_color": tenant_settings.primary_color,
            "secondary_color": tenant_settings.secondary_color
        }
    })

# POST /intake → upload + JSON response
@router.post("", response_model=IntakeResponse)
async def submit_intake(
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(""),
    address: str = Form(""),
    square_meters: float = Form(...),
    images: list[UploadFile] = File(default=[]),
    tenant_id: str = Depends(resolve_tenant),
    tenant_settings: TenantSettings = Depends(get_tenant_settings)
):
    """Submit intake form met tenant-aware file storage"""
    if square_meters <= 0:
        raise HTTPException(status_code=400, detail="square_meters must be > 0")

    # Generate lead ID
    lead_id = intake_service.generate_lead_id()
    
    # Save uploaded files using tenant-aware service
    saved_files = await intake_service.save_files(images or [], lead_id, tenant_id)
    
    # Log tenant activity
    intake_service.logger.info(f"[TENANT:{tenant_id}] Intake submitted for {name} ({email}) - {len(saved_files)} files uploaded")

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
        status="submitted"
    )

# GET /intake/stats/{tenant_id} → tenant upload statistics
@router.get("/stats/{tenant_id}")
async def get_tenant_stats(
    tenant_id: str,
    current_tenant_id: str = Depends(resolve_tenant)
):
    """Get upload statistics for a specific tenant (only accessible by that tenant)"""
    if tenant_id != current_tenant_id:
        raise HTTPException(
            status_code=403, 
            detail="You can only access statistics for your own tenant"
        )
    
    stats = intake_service.get_tenant_upload_stats(tenant_id)
    return {
        "tenant_id": tenant_id,
        "statistics": stats
    }

# GET /intake/leads → list leads for current tenant
@router.get("/leads")
async def list_tenant_leads(
    tenant_id: str = Depends(resolve_tenant),
    tenant_settings: TenantSettings = Depends(get_tenant_settings)
):
    """List all leads for the current tenant"""
    # This would typically connect to a database
    # For now, we'll return a placeholder response
    return {
        "tenant_id": tenant_id,
        "company_name": tenant_settings.company_name,
        "leads": [],
        "message": "Lead listing not yet implemented - would connect to database"
    }
