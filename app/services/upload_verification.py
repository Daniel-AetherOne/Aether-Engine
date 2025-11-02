# app/services/upload_verification.py
from botocore.exceptions import ClientError
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.services.s3 import s3_client
from app.models.upload_record import UploadRecord, UploadStatus
from app.schemas.uploads import VerifyUploadIn, UploadRecordOut


def _head_object(key: str):
    s3 = s3_client()
    return s3.head_object(Bucket=settings.s3_bucket, Key=key)


def _get_object_attributes(key: str):
    s3 = s3_client()
    # Optional, richer info (checksums/parts)
    return s3.get_object_attributes(
        Bucket=settings.s3_bucket,
        Key=key,
        ObjectAttributes=["ETag", "Checksum", "ObjectSize", "ObjectParts", "StorageClass"],
    )


def verify_and_persist(db: Session, payload: VerifyUploadIn) -> UploadRecordOut:
    # 1) HEAD object
    try:
        head = _head_object(payload.object_key)
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
            raise HTTPException(status_code=404, detail="Object not found in S3")
        raise

    size = int(head["ContentLength"])
    mime = head.get("ContentType") or "application/octet-stream"
    etag = head.get("ETag", "").strip('"')  # S3 returns quotes
    metadata = head.get("Metadata", {}) or {}

    # 2) Validations
    if payload.min_size and size < payload.min_size:
        raise HTTPException(status_code=400, detail=f"Object too small ({size} bytes)")

    if payload.expect_mime and mime != payload.expect_mime:
        raise HTTPException(status_code=400, detail=f"MIME mismatch: got {mime}, expected {payload.expect_mime}")

    if mime not in settings.allowed_mimes:
        raise HTTPException(status_code=400, detail=f"MIME not allowed: {mime}")

    max_bytes = settings.max_upload_mb * 1024 * 1024
    if size > max_bytes:
        raise HTTPException(status_code=400, detail=f"Object exceeds {settings.max_upload_mb} MB")

    # Optional: ensure lead_id in S3 user metadata matches the request
    lead_meta = metadata.get("lead_id")
    if lead_meta is not None and str(lead_meta) != str(payload.lead_id):
        raise HTTPException(status_code=400, detail="lead_id metadata mismatch")

    # Optional: cross-check client hints
    if payload.client_size is not None and int(payload.client_size) != size:
        raise HTTPException(status_code=400, detail="Size differs from client-reported")

    if payload.client_etag and payload.client_etag != etag:
        # Note: multipart uploads yield non-MD5 ETags (e.g., 'abc-5'); treat as hint only
        raise HTTPException(status_code=400, detail="ETag differs from client-reported")

    # 3) Persist UploadRecord
    record = UploadRecord(
        lead_id=payload.lead_id,
        object_key=payload.object_key,
        size=size,
        mime=mime,
        etag=etag or None,
        s3_metadata=metadata,   # <-- veldnaam hernoemd i.p.v. 'metadata'
        status=UploadStatus.uploaded,
    )

    db.add(record)
    db.commit()
    db.refresh(record)

    # 4) Return API schema (metadata gemapped naar s3_metadata)
    return UploadRecordOut(
        id=record.id,
        lead_id=record.lead_id,
        object_key=record.object_key,
        size=record.size,
        mime=record.mime,
        etag=record.etag,
        status=record.status.value,
        metadata=record.s3_metadata,  # map naar schema-veldnaam
    )
