import os
from typing import Optional
import uuid
import boto3

# ----------------------------------------------------
# Config
# ----------------------------------------------------

# Bucketnaam: accepteer zowel AWS_S3_BUCKET_NAME als AWS_S3_BUCKET, met fallback
AWS_S3_BUCKET_NAME = (
    os.getenv("AWS_S3_BUCKET_NAME")
    or os.getenv("AWS_S3_BUCKET")
    or "levelai-prod-files"
)
AWS_REGION = os.getenv("AWS_REGION", "eu-west-1")

# CloudFront: support zowel oude als nieuwe naam
_RAW_CF1 = os.getenv("AWS_CLOUDFRONT_BASE_URL")  # nieuw uit roadmap
_RAW_CF2 = os.getenv("CLOUDFRONT_DOMAIN")        # oudere naam
CLOUDFRONT_BASE_URL: Optional[str] = (
    (_RAW_CF1 or _RAW_CF2).rstrip("/") if (_RAW_CF1 or _RAW_CF2) else None
)

# Upload-limieten
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
PRESIGNED_EXPIRES_IN = 3600          # 1 uur

# Boto3 client (maakt gebruik van IAM role / env credentials)
_s3_client = boto3.client("s3")


# ----------------------------------------------------
# Upload helpers
# ----------------------------------------------------

def create_presigned_post_for_image_upload(prefix: str = "uploads/") -> dict:
    """
    Maak een presigned POST voor een image-upload met size/type restricties.
    """
    key = f"{prefix}{uuid.uuid4()}"  # bv. uploads/<uuid>

    fields = {
        "Content-Type": "image/jpeg",
        "x-amz-server-side-encryption": "AES256",
    }

    conditions = [
        ["content-length-range", 0, MAX_UPLOAD_BYTES],
        ["starts-with", "$Content-Type", "image/"],
        {"x-amz-server-side-encryption": "AES256"},
    ]

    presigned = _s3_client.generate_presigned_post(
        Bucket=AWS_S3_BUCKET_NAME,
        Key=key,
        Fields=fields,
        Conditions=conditions,
        ExpiresIn=PRESIGNED_EXPIRES_IN,
    )

    presigned["key"] = key
    return presigned


def put_bytes(
    key: str,
    data: bytes,
    content_type: str = "application/octet-stream",
    cache: Optional[str] = None,
) -> None:
    """
    Schrijf bytes naar S3 met optionele Cache-Control.
    """
    extra_args = {
        "ContentType": content_type,
        "ServerSideEncryption": "AES256",
    }
    if cache:
        extra_args["CacheControl"] = cache

    _s3_client.put_object(
        Bucket=AWS_S3_BUCKET_NAME,
        Key=key,
        Body=data,
        **extra_args,
    )


# ----------------------------------------------------
# Public URL helpers
# ----------------------------------------------------

def public_http_url(key: str) -> Optional[str]:
    """
    Bouw een publieke HTTP-URL.
    - Als CloudFront is geconfigureerd -> CloudFront URL
    - Anders: directe S3 URL (virtual-hosted style)
    """
    key = key.lstrip("/")

    # 1) CloudFront via env
    if CLOUDFRONT_BASE_URL:
        return f"{CLOUDFRONT_BASE_URL}/{key}"

    # 2) Fallback: directe S3-URL
    return f"https://{AWS_S3_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{key}"


def create_presigned_get(key: str, expires_in: int = 3600) -> str:
    """
    Maak een presigned GET-URL voor een object in S3.
    """
    return _s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": AWS_S3_BUCKET_NAME, "Key": key},
        ExpiresIn=expires_in,
    )
