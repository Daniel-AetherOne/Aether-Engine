# app/infra/s3_client.py

import os
import logging
import boto3
from botocore.config import Config

logger = logging.getLogger(__name__)

AWS_REGION = os.getenv("AWS_REGION", "eu-west-1")
S3_BUCKET  = os.getenv("S3_BUCKET", "levelai-prod-files")

_BOTO_CFG = Config(
    region_name=AWS_REGION,
    retries={"max_attempts": 5, "mode": "standard"},
    connect_timeout=3,
    read_timeout=10,
)

_s3_client = None

def get_s3():
    """Lazy singleton S3 client met standaardconfig."""
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3", config=_BOTO_CFG)
        logger.info("S3 client initialized region=%s bucket=%s", AWS_REGION, S3_BUCKET)
    return _s3_client

def get_bucket() -> str:
    return S3_BUCKET

def get_region() -> str:
    return AWS_REGION
