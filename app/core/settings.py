# app/core/settings.py
from pydantic_settings import BaseSettings, SettingsConfigDict
# from pydantic import AnyUrl   # <-- niet nodig als we str gebruiken
from typing import Optional

class Settings(BaseSettings):
    # --- Storage ---
    S3_BUCKET: str = "levelai-prod-files"
    S3_REGION: str = "eu-west-1"
    CLOUDFRONT_DOMAIN: Optional[str] = None   # mag leeg of volledige URL

    # Local storage fallback
    USE_LOCAL_STORAGE: bool = False
    LOCAL_STORAGE_ROOT: str = "./.local_storage"

    # Upload policy
    allowed_mimes: list[str] = ["image/jpeg", "image/png", "application/pdf"]
    max_upload_mb: int = 50
    presign_expiry_sec: int = 600
    allowed_metadata_keys: list[str] = ["trace_id"]

    # Multipart
    mpu_part_size_mb: int = 8

    # ✅ negeer env vars die niet in dit model staan
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

settings = Settings()  # leest .env
