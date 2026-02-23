# app/routers/uploads.py
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import PurePath
from typing import Dict, Optional
import mimetypes
from uuid import uuid4

from app.models import LeadFile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.db import get_db

from app.models import Lead
from app.models.upload_record import UploadRecord, UploadStatus

from app.services.s3_keys import _safe_filename
from app.services.storage import (
    ALLOWED_CONTENT_TYPES,
    MAX_BYTES,
    TEMP_PREFIX,
    LocalStorage,
    S3Storage,
    Storage,
    get_storage,
    head_ok,
)

# -----------------------------------------------------------------------------
# Router
# -----------------------------------------------------------------------------
router = APIRouter(prefix="/uploads", tags=["uploads"])

S3_BUCKET = settings.S3_BUCKET
S3_REGION = settings.AWS_REGION

# Spec/test: presign content types
PRESIGN_ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/pdf",
}


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
# Pydantic request models
# -----------------------------------------------------------------------------
class PresignRequest(BaseModel):
    filename: str
    content_type: Optional[str] = None
    size: Optional[int] = None
    lead_id: Optional[str] = None
    expires_in: Optional[int] = None


class UploadCompleteRequest(BaseModel):
    lead_id: int
    object_key: str  # tenant-prefixed key, bv "tenant/uploads/....jpg"


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _guess_content_type(filename: str) -> str:
    ctype, _ = mimetypes.guess_type(filename)
    return ctype or "application/octet-stream"


def _make_temp_key(filename: str) -> str:
    """
    Genereer een tijdelijke key onder TEMP_PREFIX (zonder tenant).
    Voorbeeld: 'uploads/2026-02-09/<uuid>/photo.jpg'
    Let op: tenant-prefix wordt ervoor geplakt in presign.
    """
    today = datetime.now(timezone.utc).date().isoformat()
    safe_name = _safe_filename(PurePath(filename).name)
    return f"{TEMP_PREFIX}{today}/{uuid4().hex}/{safe_name}"


def _validate_content_type(ctype: str) -> None:
    """
    Globale allowlist (kan per omgeving verschillen).
    """
    if ALLOWED_CONTENT_TYPES and ctype not in ALLOWED_CONTENT_TYPES:
        # In presign mappen we 415 -> 400 (tests verwachten 400).
        raise HTTPException(status_code=415, detail=f"unsupported_content_type:{ctype}")


def _lead_and_tenant(db: Session, lead_id: int) -> tuple[Lead, str]:
    lead = db.query(Lead).filter(Lead.id == int(lead_id)).first()
    if not lead:
        raise HTTPException(status_code=404, detail="lead_not_found")

    tenant_id = str(getattr(lead, "tenant_id", "") or "")
    if not tenant_id:
        raise HTTPException(status_code=500, detail="lead_missing_tenant_id")

    return lead, tenant_id


def _local_path_if_available(
    st: Storage, tenant_id: str, key_without_tenant: str
) -> Optional[str]:
    # Only for local storage: map storage root to actual file path if available
    if isinstance(st, LocalStorage):
        # LocalStorage usually stores under settings.LOCAL_STORAGE_DIR or st.base_dir
        base_dir = (
            getattr(st, "base_dir", None)
            or getattr(st, "root_dir", None)
            or getattr(st, "root", None)
        )
        if base_dir:
            return str(Path(str(base_dir)) / tenant_id / key_without_tenant)
    return None


# -----------------------------------------------------------------------------
# PRESIGN: frontend post JSON -> wij geven upload-instructies + keys
# -----------------------------------------------------------------------------
@router.post("/presign")
async def presign_upload(
    req: PresignRequest,
    db: Session = Depends(get_db),
    _user=Depends(require_auth),  # tests verwachten auth
) -> Dict:
    """
    Presign for intake:
    - tenant_id derived from Lead (lead_id) for multi-tenant safety
    - returns object_key (tenant-prefixed) + {url, fields} for S3 POST (of local emulation)
    """
    if not req.filename:
        raise HTTPException(status_code=400, detail="filename_required")

    if not req.lead_id:
        raise HTTPException(status_code=400, detail="lead_id_required")

    _, tenant_id = _lead_and_tenant(db, int(req.lead_id))

    ctype = req.content_type or _guess_content_type(req.filename)

    if ctype not in PRESIGN_ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail=f"unsupported_content_type:{ctype}")

    try:
        _validate_content_type(ctype)
    except HTTPException as e:
        if e.status_code == 415:
            raise HTTPException(status_code=400, detail=e.detail)
        raise

    if req.size is None or req.size <= 0 or req.size > MAX_BYTES:
        raise HTTPException(status_code=400, detail="invalid_size")

    key_without_tenant = _make_temp_key(req.filename)
    key_with_tenant = f"{tenant_id}/{key_without_tenant}"

    expires_in = req.expires_in or 60 * 5

    st = get_storage()

    # --- S3 backend ---
    if isinstance(st, S3Storage):
        if not S3_BUCKET:
            raise HTTPException(status_code=500, detail="s3_bucket_not_configured")

        try:
            import boto3  # lazy import

            s3 = boto3.client("s3", region_name=S3_REGION)

            fields = {"key": key_with_tenant, "Content-Type": ctype}
            conditions = [
                {"Content-Type": ctype},
                ["content-length-range", 1, MAX_BYTES],
                ["starts-with", "$key", f"{tenant_id}/{TEMP_PREFIX}"],
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
            "key": key_without_tenant,  # legacy (tenant-loos)
            "object_key": key_with_tenant,  # important: tenant/...
            "url": post["url"],
            "fields": post["fields"],
            "post": post,  # legacy
            "tenant_id": tenant_id,  # debug
        }

    # --- Local backend (dev/test) ---
    if isinstance(st, LocalStorage):
        # Emuleer S3 presigned POST: zelfde shape (url + fields)
        post = {
            "url": "/uploads/local",
            "fields": {
                "key": key_with_tenant,
                "tenant_id": tenant_id,
                "Content-Type": ctype,
            },
        }
        return {
            "key": key_without_tenant,
            "object_key": key_with_tenant,
            "url": post["url"],
            "fields": post["fields"],
            "post": post,
            "tenant_id": tenant_id,
        }

    raise HTTPException(status_code=500, detail="unsupported_storage_backend")


# -----------------------------------------------------------------------------
# COMPLETE: frontend calls after successful upload
# -----------------------------------------------------------------------------
@router.post("/complete")
async def complete_upload(
    req: UploadCompleteRequest,
    db: Session = Depends(get_db),
) -> Dict:
    """
    Called by frontend AFTER upload succeeds.
    Validates object exists + metadata, then writes UploadRecord + LeadFile.
    """
    _, tenant_id = _lead_and_tenant(db, int(req.lead_id))

    if not req.object_key or "/" not in req.object_key:
        raise HTTPException(status_code=400, detail="bad_object_key")

    prefix = f"{tenant_id}/"
    if not req.object_key.startswith(prefix):
        raise HTTPException(status_code=403, detail="tenant_mismatch")

    key_without_tenant = req.object_key[len(prefix) :]

    st = get_storage()

    ok, meta, err = head_ok(st, tenant_id, key_without_tenant)
    if not ok:
        raise HTTPException(status_code=400, detail=f"upload_not_verified:{err}")

    # ✅ Always define these (avoid UnboundLocalError)
    meta = meta or {}
    size_bytes = int(meta.get("ContentLength") or meta.get("size_bytes") or 0)
    content_type = (
        str(meta.get("ContentType") or meta.get("content_type") or "")
        or "application/octet-stream"
    )

    # ✅ Ensure LeadFile exists (engine reads LeadFile, not UploadRecord)
    from app.models import LeadFile  # local import avoids circulars

    lf = (
        db.query(LeadFile)
        .filter(LeadFile.lead_id == int(req.lead_id))
        .filter(LeadFile.s3_key == key_without_tenant)  # tenant-loos in DB
        .first()
    )

    if lf:
        lf.size_bytes = size_bytes or lf.size_bytes
        lf.content_type = content_type or lf.content_type
        db.add(lf)
    else:
        db.add(
            LeadFile(
                lead_id=int(req.lead_id),
                s3_key=key_without_tenant,
                size_bytes=size_bytes,
                content_type=content_type,
            )
        )

    # ✅ Upsert UploadRecord (as you already do)
    existing = (
        db.query(UploadRecord).filter(UploadRecord.object_key == req.object_key).first()
    )
    if existing:
        existing.size = size_bytes
        existing.mime = content_type or existing.mime
        existing.status = UploadStatus.uploaded
        existing.s3_metadata = meta
        db.add(existing)
        db.commit()
        return {"status": "ok", "object_key": req.object_key, "updated": True}

    rec = UploadRecord(
        tenant_id=tenant_id,
        lead_id=int(req.lead_id),
        object_key=req.object_key,
        size=size_bytes,
        mime=content_type,
        status=UploadStatus.uploaded,
        s3_metadata=meta,
    )
    db.add(rec)
    db.commit()

    return {"status": "ok", "object_key": req.object_key, "created": True}


# -----------------------------------------------------------------------------
# LOCAL upload endpoint (emuleert S3-presigned POST)
# -----------------------------------------------------------------------------
@router.post("/local")
async def local_upload(
    key: str = Form(...),  # VOLLEDIGE key met tenant, bv. "acme/uploads/....jpg"
    tenant_id: str = Form(...),
    content_type: Optional[str] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> Dict:
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
    try:
        _validate_content_type(ctype)
    except HTTPException as e:
        if e.status_code == 415:
            raise HTTPException(status_code=400, detail=e.detail)
        raise

    data = await file.read()
    if not data or len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="size_exceeded")

    tenant_prefix = f"{tenant_id}/"
    key_without_tenant = key[len(tenant_prefix) :]

    st = get_storage()
    if not isinstance(st, LocalStorage):
        raise HTTPException(status_code=400, detail="not_local_storage")

    try:
        st.save_bytes(tenant_id, key_without_tenant, data, content_type=ctype)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"local_upload_failed:{e}")

    object_key = f"{tenant_id}/{key_without_tenant}"

    existing = (
        db.query(UploadRecord).filter(UploadRecord.object_key == object_key).first()
    )
    if not existing:
        rec = UploadRecord(
            tenant_id=tenant_id,
            lead_id=0,  # optioneel: later patchen via /complete of intake
            object_key=object_key,
            size=len(data),
            mime=ctype,
            status=UploadStatus.uploaded,
            s3_metadata={"ContentLength": len(data), "ContentType": ctype},
        )
        db.add(rec)
        db.commit()

    return {
        "status": "ok",
        "key": key_without_tenant,
        "object_key": object_key,
        "size": len(data),
        "content_type": ctype,
    }
