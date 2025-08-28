# app/main.py
import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Light-weight imports die geen zware ML libs trekken
from app.logging_config import setup_logging, get_logger
from app.middleware import setup_middleware
from app.services.tenant_service import TenantService

# -----------------------------------------------------------------------------
# Logging & app basics
# -----------------------------------------------------------------------------
setup_logging()
logger = get_logger(__name__)

app = FastAPI(
    title="LevelAI SaaS",
    description="AI-powered SaaS platform for intake, prediction, pricing, and CRM integration",
    version="0.1.0",
)

# -----------------------------------------------------------------------------
# Paden / directories
# -----------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = BASE_DIR.parent / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
OFFERS_DIR = DATA_DIR / "offers"

for p in (TEMPLATES_DIR, STATIC_DIR, UPLOADS_DIR, OFFERS_DIR):
    p.mkdir(parents=True, exist_ok=True)

# -----------------------------------------------------------------------------
# Middleware & CORS
# -----------------------------------------------------------------------------
setup_middleware(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Templates & static mounts
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/files", StaticFiles(directory=str(DATA_DIR)), name="files")

# -----------------------------------------------------------------------------
# Kern endpoints die altijd beschikbaar zijn
# -----------------------------------------------------------------------------
tenant_service = TenantService()

@app.get("/")
async def root() -> dict[str, str]:
    return {"application": "LevelAI SaaS", "version": "0.1.0", "status": "running"}

@app.get("/health")
async def health():
    # Bewust zo licht mogelijk houden
    return {"status": "ok"}

@app.get("/tenants")
async def list_tenants():
    tenants = tenant_service.list_tenants()
    return {
        "tenants": [
            {"tenant_id": tid, "company_name": tenant.company_name}
            for tid, tenant in tenants.items()
        ]
    }

@app.get("/tenant/{tenant_id}")
async def get_tenant_info(tenant_id: str):
    tenant = tenant_service.get_tenant(tenant_id)
    if not tenant:
        return {"error": f"Tenant {tenant_id} not found"}
    return {
        "tenant_id": tenant.tenant_id,
        "company_name": tenant.company_name,
        "logo_url": tenant.logo_url,
        "primary_color": tenant.primary_color,
        "secondary_color": tenant.secondary_color,
        "has_hubspot": bool(tenant.hubspot_token),
    }

# -----------------------------------------------------------------------------
# Routers optioneel laden (voorkomt zware imports zoals torch/timm)
# -----------------------------------------------------------------------------
if os.getenv("LOAD_ROUTERS", "0") == "1":
    logger.info("LOAD_ROUTERS=1: applicatierouters worden geladen...")
    try:
        from app.routers import intake, predict, quote, crm, tenant, jobs, metrics

        app.include_router(intake.router, prefix="/intake", tags=["intake"])
        app.include_router(predict.router, prefix="/predict", tags=["predict"])
        app.include_router(quote.router,  prefix="/quote",   tags=["quote"])
        app.include_router(jobs.router,   prefix="/jobs",    tags=["jobs"])
        app.include_router(crm.router,    prefix="/crm",     tags=["crm"])
        app.include_router(tenant.router, prefix="/tenant",  tags=["tenant"])
        app.include_router(metrics.router, prefix="/metrics", tags=["metrics"])

        logger.info("Alle routers succesvol geladen.")
    except Exception as e:
        # We loggen de fout, maar laten de app wél met /health beschikbaar blijven
        logger.exception(f"Fout bij laden van routers: {e}")
else:
    logger.info("LOAD_ROUTERS!=1: routers NIET geladen (alleen /health en basis-endpoints actief).")

logger.info("LevelAI SaaS application started successfully")
logger.info(f"Available tenants: {list(tenant_service.list_tenants().keys())}")
