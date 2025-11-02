# s3.py (vervang je ENV/client blok + update helpers)

import os
import mimetypes
import uuid
from typing import Dict, Optional
from pathlib import Path

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError

# --- Settings i.p.v. losse getenv ---
from app.core.settings import settings

AWS_REGION = settings.S3_REGION
S3_BUCKET = settings.S3_BUCKET
# Sta zowel 'cdn.domein.nl' als 'https://cdn.domein.nl' toe; verwijder trailing slash
CLOUDFRONT_DOMAIN = (settings.CLOUDFRONT_DOMAIN or "").rstrip("/")

USE_LOCAL_STORAGE = settings.USE_LOCAL_STORAGE
LOCAL_STORAGE_ROOT = settings.LOCAL_STORAGE_ROOT

S3_UPLOAD_MAX_MB = int(os.getenv("S3_UPLOAD_MAX_MB", "25"))
S3_UPLOAD_ALLOWED = set(
    t.strip()
    for t in os.getenv("S3_UPLOAD_ALLOWED_TYPES", "").split(",")
    if t.strip()
)

# Alleen eisen dat S3 vars bestaan als we NIET in lokale modus zitten
if not USE_LOCAL_STORAGE and not S3_BUCKET:
    raise RuntimeError("S3_BUCKET ontbreekt in de environment variables")

# boto3 client (alleen als we S3 gebruiken)
s3 = None
if not USE_LOCAL_STORAGE:
    s3 = boto3.client(
        "s3",
        region_name=AWS_REGION,
        config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
    )

# --- helpers ---
def s3_key_join(*parts: str) -> str:
    """Combineer pathdelen veilig tot een S3 key."""
    return "/".join(p.strip("/").replace("..", "") for p in parts if p)

def guess_content_type(filename: str, fallback: str = "application/octet-stream") -> str:
    ctype, _ = mimetypes.guess_type(filename)
    return ctype or fallback

def random_name(prefix: str = "", ext: Optional[str] = None) -> str:
    rid = uuid.uuid4().hex
    if ext and not ext.startswith("."):
        ext = f".{ext}"
    return f"{prefix}{rid}{ext or ''}"

# --- presigned POST (upload vanaf browser) (ongewijzigd bij jou) ---
# create_presigned_post(...)

# --- presigned GET (tijdelijke download link) (ongewijzigd bij jou) ---
# create_presigned_get(...)

# --- directe upload vanuit server ---
def put_bytes(
    key: str,
    data: bytes,
    content_type: Optional[str] = None,
    cache_control: Optional[str] = None,
) -> str:
    """
    Upload bytes naar S3 of lokaal.
    Retourneert een publiek bereikbare URL (CloudFront/S3 of file:// in lokale modus).
    """
    if USE_LOCAL_STORAGE:
        path = Path(LOCAL_STORAGE_ROOT) / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return f"file://{path.resolve()}"

    extra = {"ServerSideEncryption": "AES256"}
    if content_type:
        extra["ContentType"] = content_type
    if cache_control:
        extra["CacheControl"] = cache_control
    else:
        extra["CacheControl"] = "public, max-age=60"

    try:
        assert s3 is not None
        s3.put_object(Bucket=S3_BUCKET, Key=key, Body=data, **extra)
    except (BotoCoreError, ClientError) as e:
        raise RuntimeError(f"Upload naar S3 mislukt: {e}")

    return public_http_url(key)

def object_exists(key: str) -> bool:
    if USE_LOCAL_STORAGE:
        return (Path(LOCAL_STORAGE_ROOT) / key).exists()
    try:
        assert s3 is not None
        s3.head_object(Bucket=S3_BUCKET, Key=key)
        return True
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code")
        if code in ("404", "NotFound"):
            return False
        raise

def delete_object(key: str):
    if USE_LOCAL_STORAGE:
        try:
            (Path(LOCAL_STORAGE_ROOT) / key).unlink(missing_ok=True)
        except TypeError:
            # Python <3.8 fallback
            p = Path(LOCAL_STORAGE_ROOT) / key
            if p.exists():
                p.unlink()
        return
    try:
        assert s3 is not None
        s3.delete_object(Bucket=S3_BUCKET, Key=key)
    except (BotoCoreError, ClientError) as e:
        raise RuntimeError(f"Verwijderen uit S3 mislukt: {e}")

def public_http_url(key: str) -> str:
    """
    Geef een nette publieke URL.
    - Met CloudFront (als ingesteld): respecteer of er al 'https://' staat
    - Anders: directe S3-URL
    """
    if CLOUDFRONT_DOMAIN:
        if CLOUDFRONT_DOMAIN.startswith("http://") or CLOUDFRONT_DOMAIN.startswith("https://"):
            return f"{CLOUDFRONT_DOMAIN}/{key}"
        return f"https://{CLOUDFRONT_DOMAIN}/{key}"
    return f"https://{S3_BUCKET}.s3.{AWS_REGION}.amazonaws.com/{key}"
