# app/observability/metrics.py
from fastapi import APIRouter
from starlette.responses import Response

from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

router = APIRouter(tags=["observability"])

presign_counter = Counter(
    "aether_presign_total",
    "Aantal presign requests",
    ["result"],  # success|error
)

verify_counter = Counter(
    "aether_verify_total",
    "Aantal verify requests",
    ["result"],  # success|not_found|error
)

upload_size_hist = Histogram(
    "aether_upload_size_bytes",
    "Bestandsgroottes van uploads (client gemeld)",
    buckets=(1e5, 3e5, 1e6, 3e6, 1e7, 3e7, 1e8, 3e8, 1e9),
)

latency_hist = Histogram(
    "aether_api_latency_seconds",
    "API latency per route",
    ["route"],  # e.g. /uploads/presign, /uploads/verify
)


@router.get("/metrics", include_in_schema=True)
def metrics() -> Response:
    # Prometheus expects text/plain; version=0.0.4
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
