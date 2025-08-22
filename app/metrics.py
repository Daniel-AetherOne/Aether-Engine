from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Request, Response
from typing import Optional
import time

# Request metrics
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total number of HTTP requests',
    ['method', 'endpoint', 'status_code', 'tenant_id']
)

REQUEST_LATENCY = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency in seconds',
    ['method', 'endpoint', 'tenant_id'],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

# Job metrics
JOB_COUNT = Counter(
    'celery_jobs_total',
    'Total number of Celery jobs',
    ['job_type', 'status', 'tenant_id']
)

JOB_LATENCY = Histogram(
    'celery_job_duration_seconds',
    'Celery job latency in seconds',
    ['job_type', 'tenant_id'],
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 300.0, 600.0]
)

# Vision metrics
VISION_CONFIDENCE = Gauge(
    'vision_confidence_score',
    'Vision model confidence score',
    ['model_type', 'tenant_id']
)

VISION_PROCESSING_TIME = Histogram(
    'vision_processing_duration_seconds',
    'Vision processing time in seconds',
    ['model_type', 'tenant_id'],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

# Business metrics
QUOTE_COUNT = Counter(
    'quotes_created_total',
    'Total number of quotes created',
    ['status', 'tenant_id']
)

LEAD_COUNT = Counter(
    'leads_processed_total',
    'Total number of leads processed',
    ['status', 'tenant_id']
)

# Active connections/users
ACTIVE_USERS = Gauge(
    'active_users',
    'Number of active users',
    ['tenant_id']
)

class MetricsMiddleware:
    """Middleware voor het meten van request metrics"""
    
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        start_time = time.time()
        
        # Extract tenant_id from path if available
        tenant_id = "unknown"
        path = scope.get("path", "")
        if path.startswith("/tenant/"):
            parts = path.split("/")
            if len(parts) > 2:
                tenant_id = parts[2]
        
        # Track request
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_code = message.get("status", 500)
                REQUEST_COUNT.labels(
                    method=scope.get("method", "UNKNOWN"),
                    endpoint=path,
                    status_code=status_code,
                    tenant_id=tenant_id
                ).inc()
                
                # Calculate latency
                duration = time.time() - start_time
                REQUEST_LATENCY.labels(
                    method=scope.get("method", "UNKNOWN"),
                    endpoint=path,
                    tenant_id=tenant_id
                ).observe(duration)
            
            await send(message)
        
        await self.app(scope, receive, send_wrapper)

def record_job_metrics(job_type: str, tenant_id: str, status: str, duration: float):
    """Registreer Celery job metrics"""
    JOB_COUNT.labels(
        job_type=job_type,
        status=status,
        tenant_id=tenant_id
    ).inc()
    
    JOB_LATENCY.labels(
        job_type=job_type,
        tenant_id=tenant_id
    ).observe(duration)

def record_vision_metrics(model_type: str, tenant_id: str, confidence: float, processing_time: float):
    """Registreer vision model metrics"""
    VISION_CONFIDENCE.labels(
        model_type=model_type,
        tenant_id=tenant_id
    ).set(confidence)
    
    VISION_PROCESSING_TIME.labels(
        model_type=model_type,
        tenant_id=tenant_id
    ).observe(processing_time)

def record_quote_metrics(tenant_id: str, status: str):
    """Registreer quote metrics"""
    QUOTE_COUNT.labels(
        status=status,
        tenant_id=tenant_id
    ).inc()

def record_lead_metrics(tenant_id: str, status: str):
    """Registreer lead metrics"""
    LEAD_COUNT.labels(
        status=status,
        tenant_id=tenant_id
    ).inc()

def set_active_users(tenant_id: str, count: int):
    """Zet aantal actieve gebruikers voor een tenant"""
    ACTIVE_USERS.labels(tenant_id=tenant_id).set(count)

async def metrics_endpoint():
    """Endpoint voor Prometheus metrics"""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )

def get_metrics_summary():
    """Krijg een samenvatting van alle metrics"""
    return {
        "request_count": REQUEST_COUNT._value.sum(),
        "request_latency_p95": REQUEST_LATENCY.observe(0.95),  # 95th percentile
        "job_count": JOB_COUNT._value.sum(),
        "vision_confidence_avg": VISION_CONFIDENCE._value.sum() / max(len(VISION_CONFIDENCE._value), 1),
        "quotes_created": QUOTE_COUNT._value.sum(),
        "leads_processed": LEAD_COUNT._value.sum(),
        "active_users": ACTIVE_USERS._value.sum()
    }
