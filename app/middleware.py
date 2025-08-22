from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import time
import json
from typing import Optional

from app.logging_config import get_logger, set_context, LoggingContext
from app.metrics import MetricsMiddleware, record_vision_metrics
from app.rate_limiting import get_tenant_id_from_request, get_rate_limit_info

logger = get_logger(__name__)

class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware voor context-aware logging"""
    
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        # Extract context information
        tenant_id = get_tenant_id_from_request(request)
        
        # Set logging context
        with LoggingContext(tenant_id=tenant_id):
            # Log request start
            logger.info(
                f"Request started: {request.method} {request.url.path}",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "client_ip": request.client.host if request.client else "unknown",
                    "user_agent": request.headers.get("user-agent", "unknown")
                }
            )
            
            try:
                # Process request
                response = await call_next(request)
                
                # Calculate duration
                duration = time.time() - start_time
                
                # Log successful response
                logger.info(
                    f"Request completed: {request.method} {request.url.path} - {response.status_code} ({duration:.3f}s)",
                    extra={
                        "method": request.method,
                        "path": request.url.path,
                        "status_code": response.status_code,
                        "duration": duration
                    }
                )
                
                return response
                
            except Exception as e:
                # Log error
                duration = time.time() - start_time
                logger.error(
                    f"Request failed: {request.method} {request.url.path} - {str(e)} ({duration:.3f}s)",
                    extra={
                        "method": request.method,
                        "path": request.url.path,
                        "error": str(e),
                        "duration": duration
                    }
                )
                raise

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware voor rate limiting informatie in headers"""
    
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # Add rate limit info to response headers
        tenant_id = get_tenant_id_from_request(request)
        if tenant_id:
            rate_limit_info = get_rate_limit_info(tenant_id)
            
            # Add rate limit headers
            response.headers["X-RateLimit-Limit"] = "60"
            response.headers["X-RateLimit-Remaining"] = str(
                60 - rate_limit_info.get(request.url.path, {}).get("current_requests", 0)
            )
            response.headers["X-RateLimit-Reset"] = str(
                rate_limit_info.get(request.url.path, {}).get("ttl_seconds", 0)
            )
        
        return response

class MetricsMiddlewareWrapper(BaseHTTPMiddleware):
    """Wrapper voor metrics middleware"""
    
    def __init__(self, app):
        super().__init__(app)
        self.metrics_middleware = MetricsMiddleware(app)
    
    async def dispatch(self, request: Request, call_next):
        # Use the metrics middleware
        return await self.metrics_middleware(request.scope, request.receive, request._send)

def setup_middleware(app):
    """Setup alle middleware voor de applicatie"""
    # Add custom middleware
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(RateLimitMiddleware)
    
    # Note: MetricsMiddleware wordt toegevoegd via de wrapper
    # omdat het een ASGI middleware is, geen FastAPI middleware
    
    return app
