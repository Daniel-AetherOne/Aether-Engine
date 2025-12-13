# app/routers/presigned_upload.py
from __future__ import annotations

from typing import Optional, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, constr

from app.core.settings import settings
from app.services.s3 import (
    _get_s3_client,
    generate_intake_upload_key,
)

router = APIRouter(prefix="/uploads", tags=["uploads"])


# ---------- Mock-auth dependency ----------
class User(BaseModel):
    id: str
    tenant_id: Optional[str] = None


def get_current_user() -> User:
    # TODO: vervang later door echte auth/JWT
    return User(id="test-user", tenant_id="default")


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

    bucket = (
        getattr(settings, "s3_bucket", None)
        or getattr(settings, "AWS_S3_BUCKET_NAME", None)
        or getattr(settings, "S3_BUCKET", None)
    )
    if not bucket:
        raise HTTPException(status_code=500, detail="S3 bucket ontbreekt in settings")

    # 2) Key bouwen
    object_key = generate_intake_upload_key(
        current_user.tenant_id or "default", body.filename
    )

    # 3) S3 client + presigned URL (via _get_s3_client uit s3.py)
    try:
        s3 = _get_s3_client()
    except RuntimeError as e:
        # Dit komt rechtstreeks uit s3.py als credentials/bucket ontbreken
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
        # Hier zie je nu de rauwe boto3 error terug
        raise HTTPException(status_code=500, detail=f"presign_failed: {e}")

    required_headers = {
        "Content-Type": body.content_type,
    }

    public_url = (
        f"{settings.S3_PUBLIC_BASE_URL.rstrip('/')}/{object_key}"
        if getattr(settings, "S3_PUBLIC_BASE_URL", None)
        else None
    )

    return PresignResponse(
        upload_url=url,
        headers=required_headers,
        key=object_key,
        expires_in=expires,
        public_url=public_url,
    )
