from __future__ import annotations
import io
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app.dependencies import get_s3_service
from app.services.s3 import S3Service, _guess_content_type
from app.services.s3_keys import build_upload_key

router = APIRouter(prefix="/intake", tags=["intake"])


def _get_tenant_id_from_s3(s3: S3Service) -> str:
    """
    Probeer een tenant-achtige ID uit de S3Service te halen.
    Valt terug op 'debug-tenant' als er niets is.
    """
    for attr in ("tenant_id", "tenant", "tenantId"):
        val = getattr(s3, attr, None)
        if isinstance(val, str) and val:
            return val
        if hasattr(val, "id"):
            return str(getattr(val, "id"))
    return "debug-tenant"


def _build_intake_key(s3: S3Service, lead_id: str, kind: str, filename: str) -> str:
    """
    Centrale helper voor intake-upload keys.

    We mappen:
        tenant_id  -> uit S3Service (of 'debug-tenant')
        lead_id    -> lead_id + kind (bv. "L-123-attachments")
        filename   -> originele bestandsnaam

    Resultaat (via build_upload_key):
        uploads/{tenant_id}/{lead_id-kind}/{uuid}_{sanitized_filename}
    """
    tenant_id = _get_tenant_id_from_s3(s3)
    lead_and_kind = f"{lead_id}-{kind}" if kind else lead_id
    return build_upload_key(tenant_id, lead_and_kind, filename or "upload.bin")


@router.post("/upload")
async def upload_intake_file(
    lead_id: str = Form(...),
    kind: str = Form("attachments"),
    file: UploadFile = File(...),
    s3: S3Service = Depends(get_s3_service),
):
    key = _build_intake_key(s3, lead_id=lead_id, kind=kind, filename=file.filename or "upload.bin")
    ctype = file.content_type or _guess_content_type(file.filename or "")
    try:
        data = await file.read()
        bio = io.BytesIO(data)
        s3.put_fileobj(bio, key, content_type=ctype, metadata={"lead_id": lead_id, "kind": kind})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"S3 upload failed: {e}")
    return {"ok": True, "key": key, "uri": f"s3://{s3.bucket}/{key}"}


@router.get("/upload/presign")
async def presign_upload(
    lead_id: str,
    filename: str,
    kind: str = "attachments",
    content_type: Optional[str] = None,
    max_size_mb: int = 25,
    s3: S3Service = Depends(get_s3_service),
):
    key = _build_intake_key(s3, lead_id=lead_id, kind=kind, filename=filename)
    ctype = content_type or _guess_content_type(filename)
    form = s3.presigned_post(key, content_type=ctype, max_size=max_size_mb * 1024 * 1024)
    return {"ok": True, "key": key, "form": form}


@router.get("/upload/url")
async def presign_download(key: str, s3: S3Service = Depends(get_s3_service)):
    if not s3.head(key):
        raise HTTPException(status_code=404, detail="Object not found")
    url = s3.presigned_get(key)
    return {"ok": True, "url": url}


@router.delete("/upload")
async def delete_upload(key: str, s3: S3Service = Depends(get_s3_service)):
    if not s3.head(key):
        raise HTTPException(status_code=404, detail="Object not found")
    s3.delete(key)
    return JSONResponse(status_code=204, content=None)
