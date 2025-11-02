# app/services/publisher.py
from pathlib import Path
from typing import Optional
import boto3
from botocore.client import Config

from app.core.settings import settings

class Publisher:
    """
    Dunne façade om HTML te publiceren naar S3 of lokaal (fallback).
    Wijzigt niets aan je bestaande storage.py.
    """
    def __init__(self):
        self.use_local = settings.USE_LOCAL_STORAGE
        self.bucket = settings.S3_BUCKET
        self.region = settings.S3_REGION
        self.cdn = settings.CLOUDFRONT_DOMAIN
        self.local_root = Path(settings.LOCAL_STORAGE_ROOT)

        if not self.use_local:
            self.s3 = boto3.client(
                "s3",
                region_name=self.region,
                config=Config(s3={"addressing_style": "virtual"})
            )
        else:
            self.local_root.mkdir(parents=True, exist_ok=True)

    def put_html(self, key: str, html: str, cache_control: Optional[str] = "public, max-age=60") -> str:
        """
        Schrijft HTML en retourneert de publieke URL (S3 of file://).
        """
        if self.use_local:
            target = self.local_root / key
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(html, encoding="utf-8")
            return f"file://{target.resolve()}"

        self.s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=html.encode("utf-8"),
            ContentType="text/html; charset=utf-8",
            CacheControl=cache_control
        )

        if self.cdn:
            return f"{self.cdn.rstrip('/')}/{key}"
        return f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{key}"
