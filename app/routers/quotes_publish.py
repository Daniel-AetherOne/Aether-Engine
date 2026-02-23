from datetime import datetime
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.domain.quotes import get_quote_for_publish, mark_quote_published
from app.services.s3_keys import build_quote_key, build_quote_version_key
from app.services.s3_storage import put_bytes, public_http_url, create_presigned_get

from app.verticals.registry import get as get_vertical

# Logger (brand later volledig, maar dit is alvast netjes)
logger = logging.getLogger("aether_engine.quotes")

# Metrics (optioneel)
try:
    from prometheus_client import Counter

    quotes_published_total = Counter(
        "quotes_published_total",
        "Total number of quotes successfully published",
        ["via"],
    )
    quotes_publish_error_total = Counter(
        "quotes_publish_error_total",
        "Total number of quote publish errors",
    )
except Exception:
    quotes_published_total = None
    quotes_publish_error_total = None


# Dummy auth
class CurrentUser(BaseModel):
    id: str
    is_admin: bool = True


def get_current_user() -> CurrentUser:
    return CurrentUser(id="debug-user", is_admin=True)


def _get_tenant_id_from_quote(quote) -> str:
    for attr in ("tenant_id", "tenantId", "owner_id", "ownerId"):
        val = getattr(quote, attr, None)
        if val:
            return str(val)

    tenant_obj = getattr(quote, "tenant", None)
    if isinstance(tenant_obj, dict):
        for key in ("id", "tenant_id", "tenantId"):
            v = tenant_obj.get(key)
            if v:
                return str(v)
    elif tenant_obj is not None:
        for key in ("id", "tenant_id", "tenantId"):
            v = getattr(tenant_obj, key, None)
            if v:
                return str(v)

    return "debug-tenant"


def _resolve_vertical_id_from_quote(quote) -> str:
    # Single-vertical for now, maar wél future-proof:
    lead = getattr(quote, "lead", None)
    if lead is not None:
        v = getattr(lead, "vertical", None)
        if v:
            return str(v)

    v = getattr(quote, "vertical", None)
    if v:
        return str(v)

    # fallback (jij draait nu alleen painters_us)
    return "paintly"


router = APIRouter(prefix="/quotes", tags=["quotes"])


@router.get("/{quote_id}/url")
def get_quote_url(
    quote_id: str,
    days: int = 7,
    current_user: CurrentUser = Depends(get_current_user),
):
    quote = get_quote_for_publish(quote_id)
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")

    if quote.owner_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not allowed")

    key = getattr(quote, "s3_key", None)
    if not key:
        tenant_id = _get_tenant_id_from_quote(quote)
        key = build_quote_key(tenant_id, quote.id)

    url = public_http_url(key)
    via = "cloudfront"

    if not url:
        seconds = days * 24 * 3600
        url = create_presigned_get(key, expires_in=seconds)
        via = "presigned"

    if not url:
        raise HTTPException(status_code=500, detail="Could not generate URL")

    return {"status": "ok", "quote_id": quote_id, "key": key, "url": url, "via": via}


class PublishQuoteRequest(BaseModel):
    quote_id: str
    cache_seconds: int | None = 300


class PublishQuoteResponse(BaseModel):
    status: str
    key: str
    public_url: str
    via: str
    vertical: str


@router.post("/publish", response_model=PublishQuoteResponse)
def publish_quote(
    payload: PublishQuoteRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> PublishQuoteResponse:
    cache_seconds = payload.cache_seconds or 300

    try:
        quote = get_quote_for_publish(payload.quote_id)
        if not quote:
            if quotes_publish_error_total:
                quotes_publish_error_total.inc()
            raise HTTPException(status_code=404, detail="Quote not found")

        if quote.owner_id != current_user.id and not getattr(
            current_user, "is_admin", False
        ):
            if quotes_publish_error_total:
                quotes_publish_error_total.inc()
            raise HTTPException(
                status_code=403, detail="Not allowed to publish this quote"
            )

        # ✅ Vertical-first: adapter bepaalt template/render gedrag
        vertical_id = _resolve_vertical_id_from_quote(quote)
        v = get_vertical(vertical_id)

        context = {
            "lead": quote.lead,
            "tenant": quote.tenant,
            "prediction": quote.prediction,
            "pricing": quote.pricing,
            "quote_id": quote.id,
            "current_date": quote.current_date_str,
            "validity_date": quote.validity_date_str,
        }

        html = v.render_quote_html(context)

        tenant_id = _get_tenant_id_from_quote(quote)
        ts = datetime.utcnow()

        key = build_quote_key(tenant_id, quote.id)
        version_key = build_quote_version_key(tenant_id, quote.id, ts)

        cache_control = f"public, max-age={cache_seconds}"
        data = html.encode("utf-8")

        put_bytes(
            key, data, content_type="text/html; charset=utf-8", cache=cache_control
        )
        put_bytes(
            version_key,
            data,
            content_type="text/html; charset=utf-8",
            cache=cache_control,
        )

        mark_quote_published(quote.id, s3_key=key, version_key=version_key)

        public_url = public_http_url(key)
        via = "cloudfront"
        if not public_url:
            public_url = create_presigned_get(key, expires_in=7 * 24 * 3600)
            via = "presigned"

        if not public_url:
            if quotes_publish_error_total:
                quotes_publish_error_total.inc()
            raise HTTPException(
                status_code=500, detail="Could not create public URL for quote"
            )

        logger.info(
            "Quote published",
            extra={
                "quote_id": quote.id,
                "key": key,
                "via": via,
                "vertical": vertical_id,
            },
        )
        if quotes_published_total:
            quotes_published_total.labels(via=via).inc()

        return PublishQuoteResponse(
            status="ok", key=key, public_url=public_url, via=via, vertical=vertical_id
        )

    except HTTPException:
        raise
    except Exception as exc:
        if quotes_publish_error_total:
            quotes_publish_error_total.inc()
        logger.exception(
            "Unexpected error while publishing quote",
            extra={"quote_id": payload.quote_id},
        )
        raise HTTPException(
            status_code=500, detail="Internal error while publishing quote"
        ) from exc


# ✅ Plak compat route HIER, NA publish_quote(), helemaal links (top-level)
@router.post("/publish/{quote_id}", response_model=PublishQuoteResponse)
def publish_quote_compat(
    quote_id: str,
    cache_seconds: int | None = 300,
    current_user: CurrentUser = Depends(get_current_user),
) -> PublishQuoteResponse:
    return publish_quote(
        PublishQuoteRequest(quote_id=quote_id, cache_seconds=cache_seconds),
        current_user=current_user,
    )
