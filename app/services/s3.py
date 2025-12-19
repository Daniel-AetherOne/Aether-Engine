# app/services/s3.py
import os
import uuid
import datetime as dt
from typing import Dict, Any

import boto3
from botocore.exceptions import BotoCoreError, NoCredentialsError

from app.core.settings import settings


def _get_s3_client():
    region = os.getenv("AWS_REGION", "eu-west-1")
    return boto3.client("s3", region_name=region)


def _get_bucket_name() -> str:
    bucket = (
        getattr(settings, "s3_bucket", None)
        or getattr(settings, "AWS_S3_BUCKET_NAME", None)
        or getattr(settings, "S3_BUCKET", None)
    )
    if not bucket:
        raise RuntimeError("S3 bucket ontbreekt in settings (.env)")
    return bucket


def generate_intake_upload_key(tenant_id: str, filename: str) -> str:
    today = dt.date.today().isoformat()
    unique = uuid.uuid4().hex
    return f"{tenant_id}/uploads/{today}/{unique}/{filename}"


def create_presigned_post(
    key: str,
    content_type: str,
    max_mb: int = 25,
    expires_in: int = 3600,
) -> Dict[str, Any]:
    s3 = _get_s3_client()
    bucket = _get_bucket_name()

    try:
        return s3.generate_presigned_post(
            Bucket=bucket,
            Key=key,
            Fields={"Content-Type": content_type},
            Conditions=[
                {"Content-Type": content_type},
                ["content-length-range", 1, max_mb * 1024 * 1024],
            ],
            ExpiresIn=expires_in,
        )
    except (BotoCoreError, NoCredentialsError) as e:
        raise RuntimeError(f"presign_failed: {e}") from e
