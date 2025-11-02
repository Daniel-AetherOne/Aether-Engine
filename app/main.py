# app/main.py
import asyncio
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware

# Routers (alleen de nieuwe)
from app.routers import uploads, intake

# DB & modellen
from app.db import Base, engine
from app import models  # zorgt dat SQLAlchemy modellen geregistreerd zijn

# Observability / metrics
from app.observability.metrics import router as metrics_router

# Middleware (request-id + rate limit)
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from app.middleware.request_id import RequestIdMiddleware
from app.core.rate_limit import limiter


# ----------------------------------------------------
# App init
# ----------------------------------------------------
app = FastAPI(title="LevelAI", version="0.1.0")


# ----------------------------------------------------
# Middleware
# ----------------------------------------------------
app.add_middleware(RequestIdMiddleware)   # unieke request-id header + context
app.state.limiter = limiter               # deel dezelfde limiter- instantie
app.add_middleware(SlowAPIMiddleware)     # rate-limiting

@app.exception_handler(RateLimitExceeded)
def ratelimit_handler(request: Request, exc: RateLimitExceeded):
    return PlainTextResponse(str(exc), status_code=429)

# CORS (lokaal relaxed; in productie strakker maken)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----------------------------------------------------
# Routers
# ----------------------------------------------------
# ⚠️ GEEN imports/routers uit app.api.routes.* meer
app.include_router(uploads.router)        # /uploads/presign, /uploads/local, /uploads/verify (indien aanwezig)
app.include_router(metrics_router)        # /metrics
app.include_router(intake.router)         # /intake/upload, /intake/lead


# ----------------------------------------------------
# Health
# ----------------------------------------------------
@app.get("/health", tags=["default"])
def health() -> dict:
    return {"status": "ok"}


# ----------------------------------------------------
# Startup
# ----------------------------------------------------
@app.on_event("startup")
def on_startup():
    # zorg dat tabellen bestaan (dev/SQLite); in productie via migrations
    Base.metadata.create_all(bind=engine)
