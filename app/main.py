# app/main.py
import time
import sentry_sdk

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from sentry_sdk.integrations.fastapi import FastApiIntegration

from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.core.settings import settings
from app.db import Base, engine
from app import models  # registreert SQLAlchemy modellen

from app.middleware.request_id import RequestIdMiddleware
from app.core.rate_limit import limiter

from app.core.logging_config import setup_logging, logger

# Routers
from app.routers import uploads, intake, quotes, files
from app.observability.metrics import router as metrics_router


# ----------------------------------------------------
# Sentry
# ----------------------------------------------------
sentry_sdk.init(
    dsn="https://cb47c0b6218cd9c276f3710842c418f8@o4510512134481280.ingest.de.sentry.io/4510512136800256",
    integrations=[FastApiIntegration()],
    traces_sample_rate=1.0,
    send_default_pii=True,
)


# ----------------------------------------------------
# App init
# ----------------------------------------------------
app = FastAPI(title="LevelAI", version="0.1.0")

# Configure logging (structlog -> JSON naar stdout / Cloud Run)
setup_logging()

# (optioneel) testlog voor Cloud Run
logger.info("startup_test_log", foo="bar")


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

    bound_logger.bind(
        status_code=response.status_code,
        latency_ms=latency_ms,
    ).info("request_finished")

    return response


# ----------------------------------------------------
# Middleware
# ----------------------------------------------------
app.add_middleware(RequestIdMiddleware)  # unieke request-id header + context
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)  # rate-limiting

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RateLimitExceeded)
def ratelimit_handler(request: Request, exc: RateLimitExceeded):
    return PlainTextResponse(str(exc), status_code=429)


# ----------------------------------------------------
# Routers
# ----------------------------------------------------
app.include_router(uploads.router)  # /uploads/presign, /uploads/local, ...
app.include_router(quotes.router)  # /quotes/publish/{lead_id}, /quotes/dashboard, ...
app.include_router(files.router)  # /files/...
app.include_router(intake.router)  # /intake/...
app.include_router(metrics_router)  # /metrics


# ----------------------------------------------------
# Startup
# ----------------------------------------------------
@app.on_event("startup")
def on_startup():
    # Dev/SQLite convenience; in productie liefst via migrations
    Base.metadata.create_all(bind=engine)
