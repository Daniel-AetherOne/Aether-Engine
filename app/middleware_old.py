# app/middleware.py
from __future__ import annotations

import time
import uuid
from typing import Optional, Callable, Awaitable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.logging_config import get_logger, LoggingContext
from app.rate_limiting import get_tenant_id_from_request, get_rate_limit_info

# (optioneel) metrics – stil blijven als niet aanwezig
try:
    from app.metrics import MetricsMiddleware, record_vision_metrics  # noqa: F401
    HAVE_METRICS = True
except Exception:
    HAVE_METRICS = False

logger = get_logger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Genereert/propagates X-Request-ID en zet 'm in request.state.request_id.
    Voegt de header toe aan elke response.
    """

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        req_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        request.state.request_id = req_id

        # Verwerk de request
        response: Response = await call_next(request)

        # Propagate naar client
        response.headers[REQUEST_ID_HEADER] = req_id
        return response


class LoggingMiddleware(BaseHTTPMiddleware):
    """Context-aware logging met timing en request-id."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        start_time = time.perf_counter()

        # Context info
        tenant_id = get_tenant_id_from_request(request)
        request_id = getattr(request.state, "request_id", None) or "-"

        with LoggingContext(tenant_id=tenant_id):
            # Start log
            logger.info(
                "request_started",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "client_ip": request.client.host if request.client else "unknown",
                    "user_agent": request.headers.get("user-agent", "unknown"),
                    "request_id": request_id,
                    "tenant_id": tenant_id,
                },
            )

            try:
                response: Response = await call_next(request)
                duration = (time.perf_counter() - start_time) * 1000.0

                logger.info(
                    "request_completed",
                    extra={
                        "method": request.method,
                        "path": request.url.path,
                        "status_code": getattr(response, "status_code", 0),
                        "duration_ms": round(duration, 1),
                        "request_id": request_id,
                        "tenant_id": tenant_id,
                    },
                )
                return response

            except Exception as e:
                duration = (time.perf_counter() - start_time) * 1000.0
                logger.error(
                    "request_failed",
                    extra={
                        "method": request.method,
                        "path": request.url.path,
                        "error": str(e),
                        "duration_ms": round(duration, 1),
                        "request_id": request_id,
                        "tenant_id": tenant_id,
                    },
                )
                raise


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Voegt rate-limit headers toe (per tenant & endpoint)."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        response = await call_next(request)

        tenant_id = get_tenant_id_from_request(request)
        if tenant_id:
            info = get_rate_limit_info(tenant_id)
            # Eenvoudige voorbeeldwaarden; pas aan indien je per-endpoint limieten bijhoudt
            current = info.get(request.url.path, {}).get("current_requests", 0)
            ttl = info.get(request.url.path, {}).get("ttl_seconds", 0)

            response.headers["X-RateLimit-Limit"] = "60"
            response.headers["X-RateLimit-Remaining"] = str(max(0, 60 - current))
            response.headers["X-RateLimit-Reset"] = str(ttl)

        return response


class MetricsMiddlewareWrapper(BaseHTTPMiddleware):
    """
    Wrapper voor MetricsMiddleware (ASGI). Alleen actief als app.metrics aanwezig is.
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        if HAVE_METRICS:
            self._metrics = MetricsMiddleware(app)  # type: ignore[attr-defined]
        else:
            self._metrics = None

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        # Als metrics niet beschikbaar is: val terug op de normale chain
        if not self._metrics:
            return await call_next(request)

        # Gebruik de ASGI-middleware door scope/receive/send door te geven.
        # We laten de oorspronkelijke call_next chain intact door send te intercepten.
        send_buffer = {}

        async def send_wrapper(message):
            send_buffer["message"] = message

        await self._metrics(request.scope, request.receive, send_wrapper)  # type: ignore[misc]

        # Ga alsnog door de normale handler (om consistent te blijven met BaseHTTPMiddleware)
        response = await call_next(request)

        # Als de metrics-middleware headers klaar had gezet, stuur die niet apart—response gaat de deur uit.
        return response


def setup_middleware(app):
    """Registreer alle middleware in de juiste volgorde."""
    # 1) Request ID eerst zodat iedereen 'm kan gebruiken
    app.add_middleware(RequestIDMiddleware)

    # 2) Logging (gebruikt request_id & tenant context)
    app.add_middleware(LoggingMiddleware)

    # 3) Rate limiting headers
    app.add_middleware(RateLimitMiddleware)

    # 4) Metrics (optioneel)
    app.add_middleware(MetricsMiddlewareWrapper)

    return app
