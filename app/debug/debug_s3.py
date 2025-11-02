# debug_s3.py
from fastapi import APIRouter
import os, boto3
from botocore.exceptions import ClientError

router = APIRouter(prefix="/debug", tags=["debug"])

def _s3():
    return boto3.client(
        "s3",
        region_name=os.getenv("AWS_REGION", "eu-west-1"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )

def _mask(v: str | None) -> str | None:
    if not v:
        return None
    return v[:4] + "…" + v[-4:] if len(v) > 8 else "****"

@router.get("/s3-env")
async def s3_env():
    return {
        "AWS_REGION": os.getenv("AWS_REGION"),
        "S3_BUCKET": os.getenv("S3_BUCKET"),
        "AWS_ACCESS_KEY_ID": _mask(os.getenv("AWS_ACCESS_KEY_ID")),
        "AWS_SECRET_ACCESS_KEY": _mask(os.getenv("AWS_SECRET_ACCESS_KEY")),
    }

@router.get("/s3-upload-test")
async def s3_upload_test(filename: str, content_type: str = "text/plain"):
    """Geeft een presigned PUT-URL terug (client kan direct naar S3 uploaden)."""
    bucket = os.getenv("S3_BUCKET")
    key = f"debug/{__import__('datetime').datetime.utcnow().strftime('%Y%m%d-%H%M%S')}-{filename}"
    url = _s3().generate_presigned_url(
        ClientMethod="put_object",
        Params={"Bucket": bucket, "Key": key, "ContentType": content_type},
        ExpiresIn=900,
        HttpMethod="PUT",
    )
    return {"status": "ok", "bucket": bucket, "key": key, "presigned_url": url, "content_type": content_type}

@router.get("/s3-head")
async def s3_head(key: str):
    """HEAD op object om te checken of-ie bestaat."""
    bucket = os.getenv("S3_BUCKET")
    try:
        _s3().head_object(Bucket=bucket, Key=key)
        return {"status": "ok", "exists": True, "bucket": bucket, "key": key}
    except ClientError as e:
        return {"status": "error", "exists": False, "bucket": bucket, "key": key, "message": str(e)}
