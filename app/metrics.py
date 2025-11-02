# app/metrics.py
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response

# ---------------------------
# Request metrics
# ---------------------------
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total number of HTTP requests",
    ["method", "endpoint", "status_code", "tenant_id"],
)

REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint", "tenant_id"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# ---------------------------
# Job metrics
# ---------------------------
JOB_COUNT = Counter(
    "celery_jobs_total",
    "Total number of Celery jobs",
    ["job_type", "status", "tenant_id"],
)

JOB_LATENCY = Histogram(
    "celery_job_duration_seconds",
    "Celery job latency in seconds",
    ["job_type", "tenant_id"],
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 300.0, 600.0],
)

# ---------------------------
# Vision metrics
# ---------------------------
VISION_CONFIDENCE = Gauge(
    "vision_confidence_score",
    "Vision model confidence score",
    ["model_type", "tenant_id"],
)

VISION_PROCESSING_TIME = Histogram(
    "vision_processing_duration_seconds",
    "Vision processing time in seconds",
    ["model_type", "tenant_id"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# ---------------------------
# Business metrics
# ---------------------------
QUOTE_COUNT = Counter(
    "quotes_created_total",
    "Total number of quotes created",
    ["status", "tenant_id"],
)

LEAD_COUNT = Counter(
    "leads_processed_total",
    "Total number of leads processed",
    ["status", "tenant_id"],
)

# ---------------------------
# Users / activity
# ---------------------------
ACTIVE_USERS = Gauge(
    "active_users",
    "Number of active users",
    ["tenant_id"],
)

# ---------------------------
# Helpers (te gebruiken in main.py of services)
# ---------------------------
async def metrics_endpoint():
    """Prometheus scrape endpoint (expose op /metrics in main.py)."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

def record_job_metrics(job_type: str, tenant_id: str, status: str, duration: float) -> None:
    JOB_COUNT.labels(job_type=job_type, status=status, tenant_id=tenant_id).inc()
    JOB_LATENCY.labels(job_type=job_type, tenant_id=tenant_id).observe(duration)

def record_vision_metrics(model_type: str, tenant_id: str, confidence: float, processing_time: float) -> None:
    VISION_CONFIDENCE.labels(model_type=model_type, tenant_id=tenant_id).set(confidence)
    VISION_PROCESSING_TIME.labels(model_type=model_type, tenant_id=tenant_id).observe(processing_time)

def record_quote_metrics(tenant_id: str, status: str) -> None:
    QUOTE_COUNT.labels(status=status, tenant_id=tenant_id).inc()

def record_lead_metrics(tenant_id: str, status: str) -> None:
    LEAD_COUNT.labels(status=status, tenant_id=tenant_id).inc()

def set_active_users(tenant_id: str, count: int) -> None:
    ACTIVE_USERS.labels(tenant_id=tenant_id).set(count)
