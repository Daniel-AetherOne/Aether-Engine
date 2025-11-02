import os, uuid, datetime, re
from typing import Optional
from app.config_uploads import upload_settings

# Mapping: MIME -> veilige extensie
_MIME_EXT = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "application/pdf": "pdf",
}

_SLUG_RE = re.compile(r"[^a-z0-9_-]+")

def _slugify(value: str, max_len: int = 64) -> str:
    value = (value or "").lower().strip()
    value = _SLUG_RE.sub("-", value)
    value = value.strip("-")[:max_len]
    return value or "na"

def _ext_from_mime(mime: str, fallback_filename: str) -> str:
    # 1) op basis van MIME
    if mime in _MIME_EXT:
        return _MIME_EXT[mime]
    # 2) fallback: uit bestandsnaam halen (laatste redmiddel)
    _, ext = os.path.splitext(fallback_filename or "")
    ext = ext.lower().lstrip(".")
    return ext if ext else "bin"

def build_upload_key(
    lead_id: str,
    original_filename: str,
    *,
    tenant_id: Optional[str] = None,
    content_type: Optional[str] = None,
    kind: str = "raw",
    shard: bool = False,
) -> str:
    """
    Geeft een veilige, deterministische key terug:
    uploads/{env}/{yyyy}/{mm}/{dd}/{tenant}/{lead}/{kind}/[shard]/uuid.ext
    """
    tenant = _slugify(tenant_id or "public")
    lead = _slugify(lead_id or "na")
    kind = _slugify(kind or "raw", max_len=16)

    now = datetime.datetime.utcnow()
    ext = _ext_from_mime(content_type or "", original_filename)
    ext = _slugify(ext, max_len=8)

    uid = uuid.uuid4().hex
    shard_part = f"{uid[:2]}/" if shard else ""

    key = (
        f"uploads/{upload_settings.app_env}/"
        f"{now:%Y}/{now:%m}/{now:%d}/"
        f"{tenant}/{lead}/{kind}/"
        f"{shard_part}{uid}.{ext}"
    )
    # Kleine sanity: geen dubbele slashes en maximale lengte
    key = re.sub(r"/{2,}", "/", key)
    if len(key) > 1024:
        # S3 limit (ruim) — maar praktisch haal je dit nooit
        raise ValueError("Object key too long")
    return key
