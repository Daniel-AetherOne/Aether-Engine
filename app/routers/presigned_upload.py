# app/routers/presigned_upload.py
from __future__ import annotations

from typing import Optional, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, constr

from app.core.settings import settings
from app.services.s3 import _get_s3_client, generate_intake_upload_key

router = APIRouter(prefix="/uploads", tags=["uploads"])


# ---------- Auth dependency (dev-only fallback) ----------
class User(BaseModel):
    id: str
    tenant_id: Optional[str] = None


def get_current_user() -> User:
    """
    Auth is not implemented yet.

    Hardening:
    - In production (ENABLE_DEV_ROUTES=False) this endpoint requires real auth and returns 401.
    - In dev (ENABLE_DEV_ROUTES=True) we return a deterministic dev user.
    """
    if not getattr(settings, "ENABLE_DEV_ROUTES", False):
        raise HTTPException(status_code=401, detail="Auth not configured")
    return User(id="dev-user", tenant_id="default")


# ---------- Body + Response Models ----------
class PresignRequest(BaseModel):
    filename: constr(min_length=1, max_length=255)
    content_type: constr(min_length=3, max_length=100)
    size_bytes: int = Field(gt=0, lt=1_000_000_000)


class PresignResponse(BaseModel):
    method: str = "PUT"
    upload_url: str
    headers: Dict[str, str]
    key: str
    expires_in: int
    public_url: Optional[str] = None


# ---------- Endpoints ----------
@router.get("/ping")
def ping():
    return {"ok": True}


@router.post("/presign", response_model=PresignResponse)
def create_presigned_put(
    body: PresignRequest,
    current_user: User = Depends(get_current_user),
):
    # 1) Validaties
    allowed_mimes = {
        "image/jpeg",
        "image/png",
        "image/webp",
        "application/pdf",
    }
    if body.content_type not in allowed_mimes:
        raise HTTPException(
            status_code=400,
            detail=f"content_type not allowed: {body.content_type}",
        )

    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    if body.size_bytes > max_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"file too large; max={max_bytes} bytes",
        )

    # 2) Bucket
    bucket = settings.S3_BUCKET
    if not bucket:
        raise HTTPException(status_code=500, detail="S3_BUCKET ontbreekt in settings")

    # 3) Key bouwen
    tenant_id = current_user.tenant_id or "default"
    object_key = generate_intake_upload_key(tenant_id, body.filename)

    # 4) S3 client + presigned URL
    try:
        s3 = _get_s3_client()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    expires = 600  # seconden

    try:
        url = s3.generate_presigned_url(
            ClientMethod="put_object",
            Params={
                "Bucket": bucket,
                "Key": object_key,
                "ContentType": body.content_type,
            },
            ExpiresIn=expires,
            HttpMethod="PUT",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"presign_failed: {e}")

    required_headers = {"Content-Type": body.content_type}

    public_base = getattr(settings, "S3_PUBLIC_BASE_URL", None)
    public_url = f"{public_base.rstrip('/')}/{object_key}" if public_base else None

    return PresignResponse(
        upload_url=url,
        headers=required_headers,
        key=object_key,
        expires_in=expires,
        public_url=public_url,
    )
