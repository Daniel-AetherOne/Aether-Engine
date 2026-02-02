# app/services/s3.py
import os
import uuid
import datetime as dt
from typing import Dict, Any, Optional

import boto3
from botocore.exceptions import BotoCoreError, NoCredentialsError

from app.core.settings import settings


def _aws_region() -> str:
    # Prefer settings, then env, then sane default
    return (
        getattr(settings, "AWS_REGION", None)
        or os.getenv("AWS_REGION")
        or os.getenv("AWS_DEFAULT_REGION")
        or "eu-west-1"
    )


def _aws_profile() -> Optional[str]:
    # Prefer settings, then env
    return getattr(settings, "AWS_PROFILE", None) or os.getenv("AWS_PROFILE") or None


def _get_s3_client():
    region = _aws_region()
    profile = _aws_profile()

    # Use Session so AWS_PROFILE works reliably
    if profile:
        session = boto3.Session(profile_name=profile, region_name=region)
    else:
        session = boto3.Session(region_name=region)

    # Fail-fast with a clear error if no creds are available
    creds = session.get_credentials()
    if creds is None:
        raise RuntimeError(
            "No AWS credentials found for S3 presign. "
            "Fix: run `aws configure` or set AWS_PROFILE in .env (e.g. AWS_PROFILE=default)."
        )

    return session.client("s3")


def _get_bucket_name() -> str:
    bucket = (
        getattr(settings, "s3_bucket", None)
        or getattr(settings, "AWS_S3_BUCKET_NAME", None)
        or getattr(settings, "S3_BUCKET", None)
    )
    if not bucket:
        raise RuntimeError("S3 bucket ontbreekt in settings (.env) (S3_BUCKET=...)")
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
