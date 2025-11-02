# app/routers/uploads.py
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from typing import Optional, Dict
import os
import mimetypes
from datetime import datetime
from pathlib import PurePath
from uuid import uuid4
from pydantic import BaseModel

from app.services.storage import (
    get_storage,
    Storage,
    S3Storage,
    LocalStorage,
    TEMP_PREFIX,
    MAX_BYTES,
    ALLOWED_CONTENT_TYPES,
)

# -----------------------------------------------------------------------------
# Router + globale storage instance
# -----------------------------------------------------------------------------
router = APIRouter(prefix="/uploads", tags=["uploads"])
storage: Storage = get_storage()

# -----------------------------------------------------------------------------
# Pydantic requestmodel voor presign (frontend stuurt JSON)
# -----------------------------------------------------------------------------
class PresignRequest(BaseModel):
    filename: str
    tenant_id: str = "default"
    content_type: Optional[str] = None


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
S3_BUCKET = os.getenv("S3_BUCKET")
S3_REGION = os.getenv("S3_REGION", "eu-west-1")


def _safe_filename(name: str) -> str:
    """Maak bestandsnaam URL/FS-safe."""
    name = PurePath(name).name  # strip pad
    return "".join(ch if ch.isalnum() or ch in (".", "-", "_") else "_" for ch in name)


def _guess_content_type(filename: str) -> str:
    ctype, _ = mimetypes.guess_type(filename)
    return ctype or "application/octet-stream"


def _make_temp_key(filename: str) -> str:
    """
    Genereer een tenant-LOZE tijdelijke key onder TEMP_PREFIX.
    Voorbeeld: 'uploads/2025-11-01/550e8400.../TEST.jpg'
    """
    today = datetime.utcnow().date().isoformat()
    return f"{TEMP_PREFIX}{today}/{uuid4().hex}/{_safe_filename(filename)}"


def _validate_content_type(ctype: str) -> None:
    if ALLOWED_CONTENT_TYPES and ctype not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=415, detail=f"unsupported_content_type:{ctype}")


# -----------------------------------------------------------------------------
# PRESIGN: frontend post JSON -> wij geven upload-instructies + tenant-LOZE key
# -----------------------------------------------------------------------------
@router.post("/presign")
async def presign_upload(req: PresignRequest) -> Dict:
    """
    Retourneert:
    {
      "key": "<tenant-loze-key>",
      "post": {
        "url": "/uploads/local" of S3-url,
        "fields": { ... }  # deze velden moet de client meesturen bij de upload
      }
    }
    """
    if not req.filename:
        raise HTTPException(status_code=400, detail="filename_required")

    # content-type bepalen/valideren
    ctype = req.content_type or _guess_content_type(req.filename)
    _validate_content_type(ctype)

    # key zonder tenant (die later richting /intake/lead gaat in object_keys)
    key_without_tenant = _make_temp_key(req.filename)
    # key met tenant (daadwerkelijke opslaglocatie bij upload)
    key_with_tenant = f"{req.tenant_id}/{key_without_tenant}"

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
                ExpiresIn=60 * 5,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"presign_failed:{e}")

        # Let op: we geven key ZONDER tenant terug
        return {"key": key_without_tenant, "post": post}

    # --- Local backend (dev/test) ---
    elif isinstance(storage, LocalStorage):
        post = {
            "url": "/uploads/local",
            "fields": {
                "key": key_with_tenant,        # mét tenant-prefix
                "Content-Type": ctype,
                "tenant_id": req.tenant_id,
            }
        }
        return {"key": key_without_tenant, "post": post}

    else:
        raise HTTPException(status_code=500, detail="unsupported_storage_backend")


# -----------------------------------------------------------------------------
# LOCAL upload endpoint (emuleert S3-presigned POST)
# -----------------------------------------------------------------------------
@router.post("/local")
async def local_upload(
    key: str = Form(...),                 # VOLLEDIGE key met tenant, bv. "acme/uploads/..."
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
    key_without_tenant = key[len(tenant_prefix):]

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
