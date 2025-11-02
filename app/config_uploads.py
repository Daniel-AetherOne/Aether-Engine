from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Set

class UploadSettings(BaseSettings):
    # Pydantic v2 settings:
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",          # <— onbekende env-variabelen negeren
    )

    aws_region: str = "eu-west-1"
    s3_bucket_name: str = "levelai-prod-files"
    app_env: str = "prod"

    max_upload_mb: int = 25
    allowed_upload_mime: str = "image/jpeg,image/png,application/pdf"
    require_checksum: bool = False

    @property
    def allowed_mime_set(self) -> Set[str]:
        return {m.strip() for m in self.allowed_upload_mime.split(",") if m.strip()}

upload_settings = UploadSettings()
