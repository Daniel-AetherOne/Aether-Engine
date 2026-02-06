# app/main.py
import os
import time
from typing import List

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from app.routers.auth import router as auth_router

from app.security.basic_auth import BasicAuthMiddleware
from app.security.rate_limit import SimpleRateLimitMiddleware
from app.core.settings import settings
from app.core.logging_config import setup_logging, logger
from app.core.rate_limit import limiter
from app.db import Base, engine
from app import models  # noqa: F401  (registreert SQLAlchemy modellen)
from app.middleware.request_id import RequestIdMiddleware
from app.verticals import register_verticals
from app.routers.app_me import router as app_me_router
from app.routers.app_dashboard import router as app_dashboard_router

from app.routers.debug_aws import router as debug_aws_router
from app.routers.vision_debug import router as vision_router
from app.routers import uploads, intake, quotes, files
from app.observability.metrics import router as metrics_router
from app.routers import internal


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


def try_load_ace_routers() -> List[object]:
    """
    Lazy-load ACE routers so a broken ACE module can't prevent the app from starting.
    Returns a list of router objects.
    """
    routers: List[object] = []
    try:
        from app.verticals.ace.api.audit_admin import router as ace_audit_admin_router
        from app.verticals.ace.api.datasets_admin import (
            router as ace_datasets_admin_router,
        )
        from app.verticals.ace.api.admin_data import router as ace_admin_data_router
        from app.verticals.ace.api.quote import (
            router as ace_quote_router,
            public_router as ace_public_router,
        )
        from app.verticals.ace.api.sales_ui import router as sales_ui_router
        from app.verticals.ace.api.kpi_overrides import router as ace_kpi_router
        from app.verticals.ace.api.profiles_admin import (
            router as ace_profiles_admin_router,
        )
        from app.verticals.ace.api.audit_view import router as ace_audit_view_router

        routers.extend(
            [
                ace_datasets_admin_router,
                ace_admin_data_router,
                ace_quote_router,
                sales_ui_router,
                ace_public_router,
                ace_kpi_router,
                ace_audit_admin_router,
                ace_profiles_admin_router,
                ace_audit_view_router,
            ]
        )
        return routers

    except Exception as e:
        # Never block Paintly MVP startup because ACE broke
        logger.exception("ACE router load failed; continuing without ACE", error=str(e))
        return []


# ----------------------------------------------------
# App init (SINGLETON)
# ----------------------------------------------------
setup_logging()

app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION)
register_verticals(app)
logger.info("startup", service=getattr(settings, "SERVICE_NAME", "aether-api"))


# ----------------------------------------------------
# Middleware
# ----------------------------------------------------
app.add_middleware(RequestIdMiddleware)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

# Keep this middleware; if ACE is disabled it's harmless
app.add_middleware(
    SimpleRateLimitMiddleware,
    path="/api/ace/quote/calculate",
    limit=30,
    window_seconds=60,
)

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
@app.get("/health", include_in_schema=True)
def health() -> dict:
    return {"status": "ok"}


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
app.include_router(auth_router)
app.include_router(app_me_router)
app.include_router(app_dashboard_router)

# Optional ACE routers
ACE_ENABLED = _env_truthy("ACE_ENABLED", "false")
if ACE_ENABLED:
    for r in try_load_ace_routers():
        app.include_router(r)
    logger.info("ACE_ENABLED=true (ACE routers attempted)")
else:
    logger.info("ACE_ENABLED=false (ACE routers skipped)")


# DEV-only routes (hardening)
if settings.ENABLE_DEV_ROUTES:
    app.include_router(debug_aws_router)
    app.include_router(vision_router)


# ----------------------------------------------------
# Startup
# ----------------------------------------------------
@app.on_event("startup")
def on_startup():
    # Runs at app startup (not import time)
    assert_no_static_aws_keys_in_env()
    Base.metadata.create_all(bind=engine)
