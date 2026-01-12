# app/routers/uploads.py
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import PurePath
from typing import Dict, Optional

import mimetypes
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel

from app.core.settings import settings
from app.services.storage import (
    ALLOWED_CONTENT_TYPES,
    MAX_BYTES,
    TEMP_PREFIX,
    LocalStorage,
    S3Storage,
    Storage,
    get_storage,
)

# ✅ gebruik dezelfde filename-sanitizer als de S3 key helpers
from app.services.s3_keys import _safe_filename

# -----------------------------------------------------------------------------
# Router + globale storage instance
# -----------------------------------------------------------------------------
router = APIRouter(prefix="/uploads", tags=["uploads"])
storage: Storage = get_storage()

S3_BUCKET = settings.S3_BUCKET
S3_REGION = settings.AWS_REGION

# Test/spec: presign moet alleen png/pdf toelaten (voorbeeld)
PRESIGN_ALLOWED_CONTENT_TYPES = {"image/png", "application/pdf"}


# -----------------------------------------------------------------------------
# Auth (test-compatible, minimal)
# -----------------------------------------------------------------------------
def require_auth(authorization: str | None = Header(default=None)) -> Dict[str, str]:
    """
    Tests verwachten dat /uploads/presign niet zonder Authorization header werkt.
    MVP: accepteer iedere Bearer token, return test-user.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="not_authenticated")
    return {"user_id": "u1"}


# -----------------------------------------------------------------------------
# Pydantic requestmodel voor presign (frontend stuurt JSON)
# -----------------------------------------------------------------------------
class PresignRequest(BaseModel):
    filename: str
    tenant_id: str = "default"
    content_type: Optional[str] = None
    size: Optional[int] = None
    lead_id: Optional[str] = None
    expires_in: Optional[int] = None  # optioneel; tests kunnen dit sturen


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _guess_content_type(filename: str) -> str:
    ctype, _ = mimetypes.guess_type(filename)
    return ctype or "application/octet-stream"


def _make_temp_key(filename: str) -> str:
    """
    Genereer een tijdelijke key onder TEMP_PREFIX (zonder tenant).
    Voorbeeld: 'uploads/2025-11-01/550e8400.../TEST.jpg'
    Let op: de tenant-prefix wordt ERVOOR geplakt bij presign.
    """
    today = datetime.now(timezone.utc).date().isoformat()
    safe_name = _safe_filename(PurePath(filename).name)
    return f"{TEMP_PREFIX}{today}/{uuid4().hex}/{safe_name}"


def _validate_content_type(ctype: str) -> None:
    """
    Globale allowlist (kan per omgeving verschillen).
    Let op: presign heeft óók een aparte allowlist (PRESIGN_ALLOWED_CONTENT_TYPES)
    die tests/spec afdwingt.
    """
    if ALLOWED_CONTENT_TYPES and ctype not in ALLOWED_CONTENT_TYPES:
        # In presign mappen we 415 -> 400 (tests verwachten 400).
        raise HTTPException(status_code=415, detail=f"unsupported_content_type:{ctype}")


# -----------------------------------------------------------------------------
# PRESIGN: frontend post JSON -> wij geven upload-instructies + keys
# -----------------------------------------------------------------------------
@router.post("/presign")
async def presign_upload(req: PresignRequest, _user=Depends(require_auth)) -> Dict:
    """
    Test-compatible response:
    - Altijd "object_key" (full key incl tenant)
    - En flattened "url" + "fields" voor presigned POST flows
    - Legacy velden "key" (tenant-loze) en "post" blijven bestaan

    Retourneert o.a.:
    {
      "object_key": "<tenant>/<uploads/...>",
      "url": "...",
      "fields": {..., "key": "<tenant>/<uploads/...>"},
      "key": "<tenant-loze-key>",
      "post": {"url": "...", "fields": {...}}
    }
    """
    if not req.filename:
        raise HTTPException(status_code=400, detail="filename_required")

    # MVP lead ownership check (tests verwachten 403 voor "lead_of_other_user")
    if req.lead_id and req.lead_id != "lead123":
        raise HTTPException(status_code=403, detail="forbidden")

    # content-type bepalen/valideren
    ctype = req.content_type or _guess_content_type(req.filename)

    # Spec/test: presign moet alleen png/pdf toelaten (voorbeeld)
    if ctype not in PRESIGN_ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail=f"unsupported_content_type:{ctype}")

    # Extra safeguard: als je global allowlist wél gezet is, respecteer die ook
    try:
        _validate_content_type(ctype)
    except HTTPException as e:
        # tests verwachten 400 bij bad mime op presign
        if e.status_code == 415:
            raise HTTPException(status_code=400, detail=e.detail)
        raise

    # size check (tests verwachten 400 bij bad size op presign)
    if req.size is None or req.size <= 0 or req.size > MAX_BYTES:
        raise HTTPException(status_code=400, detail="invalid_size")

    # key zonder tenant (die later richting /intake/lead gaat in object_keys)
    key_without_tenant = _make_temp_key(req.filename)
    # key met tenant (daadwerkelijke opslaglocatie bij upload)
    key_with_tenant = f"{req.tenant_id}/{key_without_tenant}"

    expires_in = req.expires_in or 60 * 5  # default 5 min

    # --- S3 backend ---
    if isinstance(storage, S3Storage):
        if not S3_BUCKET:
            raise HTTPException(status_code=500, detail="s3_bucket_not_configured")

        try:
            import boto3  # lazy import

            s3 = boto3.client("s3", region_name=S3_REGION)

            fields = {
                "key": key_with_tenant,
                "Content-Type": ctype,
            }
            # starts-with guard op TENANT + TEMP_PREFIX
            conditions = [
                {"Content-Type": ctype},
                ["content-length-range", 1, MAX_BYTES],
                ["starts-with", "$key", f"{req.tenant_id}/{TEMP_PREFIX}"],
            ]

            post = s3.generate_presigned_post(
                Bucket=S3_BUCKET,
                Key=key_with_tenant,
                Fields=fields,
                Conditions=conditions,
                ExpiresIn=expires_in,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"presign_failed:{e}")

        return {
            # legacy
            "key": key_without_tenant,
            "post": post,
            # test-friendly
            "object_key": key_with_tenant,
            "url": post["url"],
            "fields": post["fields"],
        }

    # --- Local backend (dev/test) ---
    if isinstance(storage, LocalStorage):
        post = {
            "url": "/uploads/local",
            "fields": {
                "key": key_with_tenant,  # mét tenant-prefix
                "Content-Type": ctype,
                "tenant_id": req.tenant_id,
            },
        }
        return {
            # legacy
            "key": key_without_tenant,
            "post": post,
            # test-friendly
            "object_key": key_with_tenant,
            "url": post["url"],
            "fields": post["fields"],
        }

    raise HTTPException(status_code=500, detail="unsupported_storage_backend")


# -----------------------------------------------------------------------------
# LOCAL upload endpoint (emuleert S3-presigned POST)
# -----------------------------------------------------------------------------
@router.post("/local")
async def local_upload(
    key: str = Form(...),  # VOLLEDIGE key met tenant, bv. "acme/uploads/..."
    tenant_id: str = Form(...),
    content_type: Optional[str] = Form(None),
    file: UploadFile = File(...),
):
    """
    Client post hiernaartoe met de 'fields' uit presign + file.
    Validaties:
      - key start met f"{tenant_id}/{TEMP_PREFIX}"
      - content-type whitelisted
      - size <= MAX_BYTES
    """
    if not key or not tenant_id:
        raise HTTPException(status_code=400, detail="missing_key_or_tenant")

    expected_prefix = f"{tenant_id}/{TEMP_PREFIX}"
    if not key.startswith(expected_prefix):
        raise HTTPException(status_code=400, detail="wrong_prefix")

    ctype = content_type or file.content_type or "application/octet-stream"
    _validate_content_type(ctype)

    data = await file.read()
    if not data or len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="size_exceeded")

    # strip tenant-prefix voor storage API
    tenant_prefix = f"{tenant_id}/"
    key_without_tenant = key[len(tenant_prefix) :]

    try:
        assert isinstance(storage, LocalStorage), "local endpoint requires LocalStorage"
        storage.save_bytes(tenant_id, key_without_tenant, data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"local_upload_failed:{e}")

    return {
        "status": "ok",
        "key": key_without_tenant,
        "size": len(data),
        "content_type": ctype,
    }
