# app/routers/presigned_upload.py
from __future__ import annotations
from pathlib import Path
from typing import Optional
import uuid
import datetime as dt  # (nog gebruikt in logs / kan weg als je wilt)

import boto3
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, constr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.services.s3_keys import build_upload_key

print(">> LOADING presigned_upload FROM:", __file__)

# ---------- Settings (LAZY) ----------
ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    AWS_REGION: str = "eu-west-1"
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    S3_BUCKET: Optional[str] = None
    S3_PUBLIC_BASE_URL: Optional[str] = None
    ENV: str = "prod"
    PRESIGN_EXPIRES_SECONDS: int = 600
    MAX_UPLOAD_BYTES: int = 25 * 1024 * 1024

    model_config = SettingsConfigDict(
        env_file=str(ENV_PATH),
        env_ignore_empty=True,
        extra="ignore",
    )


_settings_cache: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings_cache
    if _settings_cache is None:
        _settings_cache = Settings()
    return _settings_cache


_s3 = None


def get_s3():
    """Alleen aanmaken als we 'm echt nodig hebben."""
    global _s3
    if _s3 is not None:
        return _s3
    s = get_settings()
    if not (s.AWS_ACCESS_KEY_ID and s.AWS_SECRET_ACCESS_KEY and s.S3_BUCKET):
        raise HTTPException(status_code=500, detail="S3 is niet geconfigureerd")
    _s3 = boto3.client(
        "s3",
        region_name=s.AWS_REGION,
        aws_access_key_id=s.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=s.AWS_SECRET_ACCESS_KEY,
    )
    return _s3


# ---------- Router ----------
router = APIRouter(prefix="/uploads", tags=["uploads"])


@router.get("/ping")
def ping():
    return {"ok": True}


# ---------- Mock-auth dependency ----------
class User(BaseModel):
    id: str
    tenant_id: Optional[str] = None


def get_current_user() -> User:
    # TODO: vervang later door echte auth/JWT
    return User(id="test-user", tenant_id="demo-tenant")


# ---------- Body + Response Models ----------
class PresignRequest(BaseModel):
    filename: constr(min_length=1, max_length=255)
    content_type: constr(min_length=3, max_length=100)
    size_bytes: int = Field(gt=0, lt=1_000_000_000)


class PresignResponse(BaseModel):
    method: str = "PUT"
    upload_url: str
    headers: dict
    key: str
    expires_in: int
    public_url: str | None = None


# ---------- Helper ----------
def build_object_key(user: User, filename: str) -> str:
    """
    Genereer de object key via de centrale helper:
    uploads/{tenant_id}/{user_id}/{uuid}_{sanitized_filename}
    """
    tenant_id = user.tenant_id or "no-tenant"
    user_or_lead_id = user.id
    return build_upload_key(tenant_id, user_or_lead_id, filename)


# ---------- Endpoint ----------
@router.post("/presign", response_model=PresignResponse)
def create_presigned_put(
    body: PresignRequest,
    current_user: User = Depends(get_current_user),
):
    settings = get_settings()

    allowed_mimes = {
        "image/jpeg",
        "image/png",
        "image/webp",
        "application/pdf",
        "text/plain",
    }
    if body.content_type not in allowed_mimes:
        raise HTTPException(
            status_code=400,
            detail=f"content_type not allowed: {body.content_type}",
        )

    if body.size_bytes > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"file too large; max={settings.MAX_UPLOAD_BYTES} bytes",
        )

    object_key = build_object_key(current_user, body.filename)
    s3 = get_s3()
    expires = settings.PRESIGN_EXPIRES_SECONDS

    url = s3.generate_presigned_url(
        ClientMethod="put_object",
        Params={
            "Bucket": settings.S3_BUCKET,
            "Key": object_key,
            "ContentType": body.content_type,
        },
        ExpiresIn=expires,
        HttpMethod="PUT",
    )

    required_headers = {
        "Content-Type": body.content_type,
    }

    public_url = (
        f"{settings.S3_PUBLIC_BASE_URL.rstrip('/')}/{object_key}"
        if settings.S3_PUBLIC_BASE_URL and object_key
        else None
    )

    return PresignResponse(
        upload_url=url,
        headers=required_headers,
        key=object_key,
        expires_in=expires,
        public_url=public_url,
    )
