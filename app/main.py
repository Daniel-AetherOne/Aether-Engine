# app/main.py
import os
import time

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, RedirectResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from app.routers.auth import router as auth_router
from app.verticals.paintly.router_app import router as paintly_app_router
from app.routers.public_estimate import router as public_estimate_router
from app.models.job import Job
from app.jobs.runner import start_worker
from app.routers.quote_debug import router as quote_router
from app.routers import tenant_pricing
from app.routers import onboarding
from app.routers import public_intake
from app.routers.debug_email import router as debug_email_router

from app.security.basic_auth import BasicAuthMiddleware
from app.core.settings import settings
from app.core.logging_config import setup_logging, logger
from app.core.rate_limit import limiter
from app.db import Base, engine
from app import models  # noqa: F401  (registreert SQLAlchemy modellen)
from app.middleware.request_id import RequestIdMiddleware
from app.verticals import register_verticals
from app.routers.app_me import router as app_me_router
from app.routers import settings_pricing_page
from fastapi.templating import Jinja2Templates

from fastapi.staticfiles import StaticFiles

# from app.routers.app_dashboard import router as app_dashboard_router

from app.routers.debug_aws import router as debug_aws_router
from app.routers.vision_debug import router as vision_router
from app.routers import uploads, intake, quotes, files
from app.routers import billing
from app.routers import stripe_webhook
from app.observability.metrics import router as metrics_router
from app.routers import internal
from app.routers import processing


# --- AWS safety guard (geen static keys) ---
def assert_no_static_aws_keys_in_env():
    banned = ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN")
    present = [k for k in banned if os.getenv(k)]
    if present:
        raise RuntimeError(
            f"Static AWS keys found in env: {present}. "
            "Use AWS_PROFILE (local) or IAM Role / WIF (prod)."
        )


def _env_truthy(name: str, default: str = "false") -> bool:
    val = (os.getenv(name, default) or "").strip().lower()
    return val in ("1", "true", "yes", "y", "on")


# ----------------------------------------------------
# App init (SINGLETON)
# ----------------------------------------------------
setup_logging()

app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION)
register_verticals(app)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

logger.info("startup", service=getattr(settings, "SERVICE_NAME", "aether-api"))


app.state.templates = Jinja2Templates(directory="app/templates")


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/app")


# ----------------------------------------------------
# Middleware
# ----------------------------------------------------
app.add_middleware(RequestIdMiddleware)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    BasicAuthMiddleware,
    protected_prefixes=[
        "/sales",
        "/api",
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RateLimitExceeded)
def ratelimit_handler(request: Request, exc: RateLimitExceeded):
    return PlainTextResponse(str(exc), status_code=429)


# ----------------------------------------------------
# Health
# ----------------------------------------------------
@app.get("/health", include_in_schema=False)
def health() -> dict:
    return {"status": "ok", "service": "paintly-api"}


# ----------------------------------------------------
# Logging middleware
# ----------------------------------------------------
@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    start = time.time()

    request_id = getattr(request.state, "request_id", None) or request.headers.get(
        "X-Request-ID", "unknown"
    )
    tenant_id = request.headers.get("X-Tenant-ID", "unknown")
    client_ip = request.client.host if request.client else "unknown"

    bound_logger = logger.bind(
        request_id=request_id,
        tenant_id=tenant_id,
        ip=client_ip,
        endpoint=str(request.url.path),
        method=request.method,
    )

    bound_logger.info("request_started")
    response = await call_next(request)
    latency_ms = round((time.time() - start) * 1000, 2)

    bound_logger.bind(status_code=response.status_code, latency_ms=latency_ms).info(
        "request_finished"
    )
    return response


# ----------------------------------------------------
# Routers (Paintly MVP core)
# ----------------------------------------------------
app.include_router(uploads.router)
app.include_router(quotes.router)
app.include_router(files.router)
app.include_router(intake.router)
app.include_router(metrics_router)  # /metrics
app.include_router(internal.router)
app.include_router(processing.router)
app.include_router(auth_router)
app.include_router(app_me_router)
app.include_router(tenant_pricing.router)
app.include_router(settings_pricing_page.router)
app.include_router(public_intake.router)
app.include_router(debug_email_router)
# app.include_router(app_dashboard_router)
app.include_router(paintly_app_router)
app.include_router(public_estimate_router)
app.include_router(quote_router)
app.include_router(onboarding.router)
app.include_router(billing.router)
app.include_router(stripe_webhook.router)


# DEV-only routes (hardening)
if settings.ENABLE_DEV_ROUTES:
    app.include_router(debug_aws_router)
    app.include_router(vision_router)


# ----------------------------------------------------
# Startup
# ----------------------------------------------------
@app.on_event("startup")
def on_startup():
    assert_no_static_aws_keys_in_env()
    # Only auto-create tables when explicitly enabled (default: true for local dev).
    # In multi-worker Gunicorn deployments with SQLite, set
    # SQLALCHEMY_CREATE_ALL_AT_STARTUP=false to avoid concurrent schema creation.
    if _env_truthy("SQLALCHEMY_CREATE_ALL_AT_STARTUP", "true"):
        Base.metadata.create_all(bind=engine)

    # start background worker (dev)
    start_worker()
