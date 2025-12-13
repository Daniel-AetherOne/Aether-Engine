# app/services/s3.py
from typing import Dict, Any
import uuid
import datetime as dt

import boto3
from botocore.exceptions import BotoCoreError, NoCredentialsError

from app.core.settings import settings


def _get_s3_client():
    """
    Maak expliciet een S3 client met credentials uit .env / settings.
    We gebruiken de attributen zoals ze in settings heten (lowercase),
    en vallen desnoods terug op de UPPERCASE varianten.
    """
    access_key = getattr(settings, "aws_access_key_id", None) or getattr(
        settings, "AWS_ACCESS_KEY_ID", None
    )
    secret_key = getattr(settings, "aws_secret_access_key", None) or getattr(
        settings, "AWS_SECRET_ACCESS_KEY", None
    )
    region = (
        getattr(settings, "aws_region", None)
        or getattr(settings, "AWS_REGION", None)
        or "eu-west-1"
    )

    if not access_key or not secret_key:
        # Dit willen we expliciet zien als het misgaat
        raise RuntimeError(
            f"AWS credentials ontbreken in settings (.env) "
            f"(id={access_key!r}, secret_set={bool(secret_key)})"
        )

    return boto3.client(
        "s3",
        region_name=region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
    )


def _get_bucket_name() -> str:
    """
    Haal de bucketnaam uit settings (.env). Ondersteunt zowel
    S3_BUCKET als AWS_S3_BUCKET_NAME.
    """
    bucket = (
        getattr(settings, "s3_bucket", None)
        or getattr(settings, "AWS_S3_BUCKET_NAME", None)
        or getattr(settings, "S3_BUCKET", None)
    )
    if not bucket:
        raise RuntimeError("S3 bucket ontbreekt in settings (.env)")
    return bucket


def generate_intake_upload_key(tenant_id: str, filename: str) -> str:
    """
    Genereer een nette S3 key voor intake uploads.
    """
    today = dt.date.today().isoformat()
    unique = uuid.uuid4().hex
    return f"{tenant_id}/uploads/{today}/{unique}/{filename}"


def create_presigned_post(
    key: str, content_type: str, max_mb: int = 25, expires_in: int = 3600
) -> Dict[str, Any]:
    """
    Maak een S3 presigned POST voor uploads.
    (Wordt gebruikt als je ergens generate_presigned_post gebruikt; voor PUT
    gebruik je generate_presigned_url in je router.)
    """
    s3_client = _get_s3_client()
    bucket = _get_bucket_name()

    try:
        post = s3_client.generate_presigned_post(
            Bucket=bucket,
            Key=key,
            Fields={
                "Content-Type": content_type,
            },
            Conditions=[
                {"Content-Type": content_type},
                ["content-length-range", 1, max_mb * 1024 * 1024],
            ],
            ExpiresIn=expires_in,
        )
        return post
    except (BotoCoreError, NoCredentialsError) as e:
        raise RuntimeError(f"presign_failed: {e}") from e
