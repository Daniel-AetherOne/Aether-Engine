# app/services/multipart.py
from uuid import uuid4
from app.core.settings import settings
from app.services.s3 import s3_client

def _object_key_for(lead_id: int, content_type: str) -> str:
    ext = {"image/jpeg":"jpg","image/png":"png","application/pdf":"pdf"}.get(content_type, "bin")
    return f"leads/{lead_id}/{uuid4().hex}.{ext}"

def start_mpu(lead_id: int, content_type: str, metadata: dict[str,str]|None) -> tuple[str,str,int]:
    s3 = s3_client()
    key = _object_key_for(lead_id, content_type)
    usermeta = {"lead_id": str(lead_id)}
    if metadata:
        for k,v in metadata.items():
            if k in settings.allowed_metadata_keys and isinstance(v,str) and len(v)<=256:
                usermeta[k] = v

    resp = s3.create_multipart_upload(
        Bucket=settings.s3_bucket,
        Key=key,
        ContentType=content_type,
        Metadata=usermeta,
        **({"ServerSideEncryption":"aws:kms","SSEKMSKeyId":settings.s3_kms_key_id} if settings.s3_kms_key_id else {})
    )
    return resp["UploadId"], key, settings.mpu_part_size_mb * 1024 * 1024

def get_part_urls(object_key: str, upload_id: str, part_numbers: list[int]) -> list[dict]:
    s3 = s3_client()
    out = []
    for n in part_numbers:
        url = s3.generate_presigned_url(
            "upload_part",
            Params={"Bucket": settings.s3_bucket, "Key": object_key, "UploadId": upload_id, "PartNumber": n},
            ExpiresIn=settings.presign_expiry_sec,
        )
        out.append({"part_number": n, "url": url})
    return out

def complete_mpu(object_key: str, upload_id: str, parts: list[dict]):
    # parts: [{part_number, etag}]
    s3 = s3_client()
    # S3 expects ETags EXACT zoals ontvangen (incl. quotes soms door SDK – laat ze staan zoals client ze teruggeeft)
    part_list = [{"ETag": p["etag"], "PartNumber": int(p["part_number"])} for p in parts]
    return s3.complete_multipart_upload(
        Bucket=settings.s3_bucket,
        Key=object_key,
        UploadId=upload_id,
        MultipartUpload={"Parts": sorted(part_list, key=lambda x: x["PartNumber"])},
    )

def abort_mpu(object_key: str, upload_id: str):
    s3 = s3_client()
    s3.abort_multipart_upload(Bucket=settings.s3_bucket, Key=object_key, UploadId=upload_id)
