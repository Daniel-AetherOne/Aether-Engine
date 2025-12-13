from datetime import datetime
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.config.cache_config import CACHE_OFFERTES
from app.utils.cache_control import cache_control

from app.templates import render_template
from app.domain.quotes import get_quote_for_publish, mark_quote_published
from app.services.s3_keys import (
    build_quote_key,
    build_quote_version_key,
)
from app.services.s3_storage import (
    put_bytes,
    public_http_url,
    create_presigned_get,
)


put_bytes(
    key, data, content_type="text/html; charset=utf-8", cache=cache_control, public=True
)
put_bytes(
    version_key,
    data,
    content_type="text/html; charset=utf-8",
    cache=cache_control,
    public=True,
)

# Logger voor quotes
logger = logging.getLogger("levelai.quotes")

# Metrics (optioneel, als prometheus_client beschikbaar is)
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
except Exception:  # ImportError of iets anders
    quotes_published_total = None
    quotes_publish_error_total = None


# Tijdelijke dummy user voor stap 4.x – later vervangen door echte auth
class CurrentUser(BaseModel):
    id: str
    is_admin: bool = True


def get_current_user() -> CurrentUser:
    return CurrentUser(id="debug-user", is_admin=True)


def _get_tenant_id_from_quote(quote) -> str:
    """
    Haalt op een defensieve manier een tenant-achtige ID uit de quote.
    Valt terug op 'debug-tenant' als niets gevonden wordt.
    """
    # 1) Directe attributen op de quote zelf
    for attr in ("tenant_id", "tenantId", "owner_id", "ownerId"):
        val = getattr(quote, attr, None)
        if val:
            return str(val)

    # 2) Nested tenant object of dict
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

    # 3) Hele veilige fallback
    return "debug-tenant"


router = APIRouter(prefix="/quotes", tags=["quotes"])


# 4.6 – URL ophalen
@router.get("/{quote_id}/url")
def get_quote_url(
    quote_id: str,
    days: int = 7,
    current_user: CurrentUser = Depends(get_current_user),
):
    # 1. Quote ophalen + autorisatie
    quote = get_quote_for_publish(quote_id)
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")

    if quote.owner_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not allowed")

    # 2. S3 key bepalen
    key = getattr(quote, "s3_key", None)
    if not key:
        tenant_id = _get_tenant_id_from_quote(quote)
        key = build_quote_key(tenant_id, quote.id)

    # 3. CloudFront of presigned GET
    url = public_http_url(key)
    via = "cloudfront"

    if not url:
        seconds = days * 24 * 3600
        url = create_presigned_get(key, expires_in=seconds)
        via = "presigned"

    if not url:
        raise HTTPException(
            status_code=500,
            detail="Could not generate URL",
        )

    return {
        "status": "ok",
        "quote_id": quote_id,
        "key": key,
        "url": url,
        "via": via,
    }


# 4.5 – Publiceren
class PublishQuoteRequest(BaseModel):
    quote_id: str
    cache_seconds: int | None = 300


class PublishQuoteResponse(BaseModel):
    status: str
    key: str
    public_url: str
    via: str


@router.post("/publish", response_model=PublishQuoteResponse)
def publish_quote(
    payload: PublishQuoteRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> PublishQuoteResponse:
    # cache_seconds alvast bepalen (ook handig voor logging)
    cache_seconds = payload.cache_seconds or 300

    try:
        # 1. Quote ophalen & autorisatie check
        quote = get_quote_for_publish(payload.quote_id)
        if not quote:
            if quotes_publish_error_total:
                quotes_publish_error_total.inc()
            logger.warning(
                "Publish failed: quote not found",
                extra={"quote_id": payload.quote_id},
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Quote not found",
            )

        if quote.owner_id != current_user.id and not getattr(
            current_user, "is_admin", False
        ):
            if quotes_publish_error_total:
                quotes_publish_error_total.inc()
            logger.warning(
                "Publish forbidden: not owner or admin",
                extra={
                    "quote_id": quote.id,
                    "user_id": current_user.id,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not allowed to publish this quote",
            )

        # 2. HTML renderen
        context = {
            "lead": quote.lead,
            "tenant": quote.tenant,
            "prediction": quote.prediction,
            "pricing": quote.pricing,
            "quote_id": quote.id,
            "current_date": quote.current_date_str,
            "validity_date": quote.validity_date_str,
        }

        html = render_template("quote.html", context)

        # 3. S3 keys bepalen (tenant + quote)
        tenant_id = _get_tenant_id_from_quote(quote)
        ts = datetime.utcnow()

        key = build_quote_key(tenant_id, quote.id)
        version_key = build_quote_version_key(tenant_id, quote.id, ts)

        # 4. Uploaden naar S3
        cache_control = f"public, max-age={cache_seconds}"
        data = html.encode("utf-8")

        # Latest (index.html)
        put_bytes(
            key,
            data,
            content_type="text/html; charset=utf-8",
            cache=cache_control,
        )

        # Versie-archief
        put_bytes(
            version_key,
            data,
            content_type="text/html; charset=utf-8",
            cache=cache_control,
        )

        # 5. Quote markeren als gepubliceerd
        mark_quote_published(quote.id, s3_key=key, version_key=version_key)

        # 6. URL kiezen: CloudFront public URL of presigned
        public_url = public_http_url(key)
        via = "cloudfront"

        if not public_url:
            expires_in = 7 * 24 * 3600  # 7 dagen
            public_url = create_presigned_get(key, expires_in=expires_in)
            via = "presigned"

        if not public_url:
            if quotes_publish_error_total:
                quotes_publish_error_total.inc()
            logger.error(
                "Publish failed: could not create public URL",
                extra={
                    "quote_id": quote.id,
                    "key": key,
                    "cache_seconds": cache_seconds,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Could not create public URL for quote",
            )

        # 7. Success logging + metric
        logger.info(
            "Quote published",
            extra={
                "quote_id": quote.id,
                "key": key,
                "via": via,
                "cache_seconds": cache_seconds,
            },
        )
        if quotes_published_total:
            quotes_published_total.labels(via=via).inc()

        return PublishQuoteResponse(
            status="ok",
            key=key,
            public_url=public_url,
            via=via,
        )

    except HTTPException:
        # HTTPExceptions zijn al voorzien van correcte statuscode;
        # errors zijn hierboven al meegeteld.
        raise
    except Exception as exc:
        # Onverwachte fout
        if quotes_publish_error_total:
            quotes_publish_error_total.inc()
        logger.exception(
            "Unexpected error while publishing quote",
            extra={
                "quote_id": payload.quote_id,
                "cache_seconds": cache_seconds,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error while publishing quote",
        ) from exc
