# app/routers/files.py
from typing import Dict, Any
from uuid import uuid4

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

from app.core.settings import settings
from app.services.s3 import generate_intake_upload_key, create_presigned_post

router = APIRouter(prefix="/files", tags=["files"])


class PresignUploadResponse(BaseModel):
    url: str
    fields: Dict[str, Any]
    key: str


@router.get("/presign-upload", response_model=PresignUploadResponse)
def presign_upload(
    filename: str = Query(...),
    content_type: str = Query("image/jpeg"),
    size_bytes: int = Query(0),
):
    """
    Legacy endpoint voor de intake upload widget.
    Wordt aangeroepen als:
      GET /files/presign-upload?filename=...&content_type=...&size_bytes=...

    Retourneert een S3 presigned POST:
      { "url": ..., "fields": {...}, "key": ... }
    """

    # 1) Validaties
    allowed_mimes = {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/gif",
        "image/bmp",
    }
    if content_type not in allowed_mimes:
        raise HTTPException(
            status_code=400,
            detail=f"content_type not allowed: {content_type}",
        )

    max_mb = getattr(settings, "S3_UPLOAD_MAX_MB", 25)
    max_bytes = max_mb * 1024 * 1024
    if size_bytes and size_bytes > max_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"file too large; max={max_bytes} bytes",
        )

    # 2) S3 key opbouwen (tenant nu gewoon 'default')
    tenant_id = "default"
    key = generate_intake_upload_key(tenant_id, filename)

    # 3) Presigned POST maken via onze centrale S3 helper
    try:
        presigned = create_presigned_post(
            key=key,
            content_type=content_type,
            max_mb=max_mb,
        )
    except RuntimeError as e:
        # komt rechtstreeks uit create_presigned_post (credentials, bucket etc.)
        raise HTTPException(status_code=500, detail=str(e))

    return PresignUploadResponse(
        url=presigned["url"],
        fields=presigned["fields"],
        key=key,
    )
