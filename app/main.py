from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.routers import intake, predict, quote, crm, tenant, jobs, metrics
from app.services.tenant_service import TenantService
from app.logging_config import setup_logging, get_logger
from app.middleware import setup_middleware
from app.metrics import MetricsMiddleware

# Setup Loguru logging
setup_logging()
logger = get_logger(__name__)

app = FastAPI(
    title="LevelAI SaaS",
    description="AI-powered SaaS platform for intake, prediction, pricing, and CRM integration",
    version="0.1.0"
)

# Pad-opbouw vanaf dit bestand
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = BASE_DIR.parent / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
OFFERS_DIR = DATA_DIR / "offers"

# Initialize tenant service
tenant_service = TenantService()

# Zorg dat deze mappen bestaan
for p in (TEMPLATES_DIR, STATIC_DIR, UPLOADS_DIR, OFFERS_DIR):
    p.mkdir(parents=True, exist_ok=True)

# Create tenant-specific directories for all configured tenants
logger.info("Setting up tenant-specific directories...")
for tenant_id in tenant_service.list_tenants():
    tenant_service.ensure_tenant_directories(tenant_id, ["data/uploads", "data/offers"])
    logger.info(f"Created directories for tenant: {tenant_id}")

# Setup custom middleware
setup_middleware(app)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Templates & static
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Mount offers directory voor public toegang
app.mount("/files", StaticFiles(directory=str(DATA_DIR)), name="files")

@app.get("/")
async def root() -> dict[str, str]:
    return {"application": "LevelAI SaaS", "version": "0.1.0", "status": "running"}

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/tenants")
async def list_tenants():
    """List all available tenants"""
    tenants = tenant_service.list_tenants()
    return {
        "tenants": [{"tenant_id": tid, "company_name": tenant.company_name} 
                   for tid, tenant in tenants.items()]
    }

@app.get("/tenant/{tenant_id}")
async def get_tenant_info(tenant_id: str):
    """Get specific tenant information"""
    tenant = tenant_service.get_tenant(tenant_id)
    if not tenant:
        return {"error": f"Tenant {tenant_id} not found"}
    
    return {
        "tenant_id": tenant.tenant_id,
        "company_name": tenant.company_name,
        "logo_url": tenant.logo_url,
        "primary_color": tenant.primary_color,
        "secondary_color": tenant.secondary_color,
        "has_hubspot": bool(tenant.hubspot_token)
    }

# Intake router
app.include_router(intake.router, prefix="/intake", tags=["intake"])

# Predict router
app.include_router(predict.router, prefix="/predict", tags=["predict"])

# Quote router
app.include_router(quote.router, prefix="/quote", tags=["quote"])

# Jobs router
app.include_router(jobs.router, prefix="/jobs", tags=["jobs"])

# CRM router
app.include_router(crm.router, prefix="/crm", tags=["crm"])

# Tenant router
app.include_router(tenant.router, prefix="/tenant", tags=["tenant"])

# Metrics router
app.include_router(metrics.router, prefix="/metrics", tags=["metrics"])

logger.info("LevelAI SaaS application started successfully")
logger.info(f"Available tenants: {list(tenant_service.list_tenants().keys())}")
