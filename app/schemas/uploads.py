# app/schemas/uploads.py
from pydantic import BaseModel, Field

class VerifyUploadIn(BaseModel):
    lead_id: int
    object_key: str
    expect_mime: str | None = None
    min_size: int | None = 1
    # Optional: echo back values you calculated client-side for extra safety
    client_size: int | None = None
    client_etag: str | None = None  # from multipart uploader if available

class UploadRecordOut(BaseModel):
    id: int
    lead_id: int
    object_key: str
    size: int
    mime: str
    etag: str | None
    status: str
    metadata: dict | None

from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Literal

ALLOWED_MIME = {"image/jpeg", "image/png", "application/pdf"}

class UploadInitRequest(BaseModel):
    filename: str
    mime_type: str
    size_bytes: int
    content_disposition: Literal["inline", "attachment"] = "inline"

    @field_validator("mime_type")
    @classmethod
    def validate_mime(cls, v):
        if v not in ALLOWED_MIME:
            raise ValueError("MIME type not allowed")
        return v

    @field_validator("size_bytes")
    @classmethod
    def validate_size(cls, v):
        if v <= 0 or v > 1024 * 1024 * 1024 * 2:  # harde bovengrens 2GB als safeguard
            raise ValueError("Invalid size")
        return v

class PresignedPut(BaseModel):
    url: str
    headers: dict
    expires_in_seconds: int

class UploadInitResponse(BaseModel):
    file_id: str
    s3_key: str
    mode: Literal["single", "multipart"]
    put: PresignedPut | None = None
    parts: list[dict] | None = None  # voor multipart

class UploadCompleteRequest(BaseModel):
    file_id: str
    checksum_sha256_b64: str | None = None  # client stuurt mee wat hij gebruikte
    etag: str | None = None
