# app/core/settings.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyHttpUrl
from typing import Optional


class Settings(BaseSettings):
    PUBLIC_BASE_URL: AnyHttpUrl = "http://localhost:8000"

    # --- Storage ---
    S3_BUCKET: str = "levelai-prod-files"
    S3_REGION: str = "eu-west-1"
    CLOUDFRONT_DOMAIN: Optional[str] = None
    USE_LOCAL_STORAGE: bool = False
    LOCAL_STORAGE_ROOT: str = "./.local_storage"

    allowed_mimes: list[str] = ["image/jpeg", "image/png", "application/pdf"]
    max_upload_mb: int = 50
    presign_expiry_sec: int = 600
    allowed_metadata_keys: list[str] = ["trace_id"]
    mpu_part_size_mb: int = 8

    # --- E-mail (nieuw) ---
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM_EMAIL: Optional[str] = None
    SMTP_FROM_NAME: str = "LevelAI"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()  # leest .env
