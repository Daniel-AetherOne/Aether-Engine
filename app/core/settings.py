# app/core/settings.py
from typing import Optional, List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- Core app ---
    ENV: str = "development"
    APP_ENV: str = "development"
    APP_NAME: str = "Aether Engine"
    APP_VERSION: str = "0.1.0"
    SERVICE_NAME: str = "aether-api"
    ENABLE_DEV_ROUTES: bool = False
    ENABLE_LLM_PRICING: bool = False

    AWS_PROFILE: Optional[str] = None
    AWS_SESSION_TOKEN: Optional[str] = None

    # Postmark
    POSTMARK_SERVER_TOKEN: str = ""
    POSTMARK_FROM: str = ""
    POSTMARK_REPLY_TO: str = ""
    APP_PUBLIC_BASE_URL: str = "http://127.0.0.1:8000"

    # Public estimate flow
    SEND_ACCEPT_CONFIRMATION_EMAIL: bool = True

    # Security-critical (geen defaults)
    JWT_SECRET: str
    SECRET_KEY: str
    JWT_EXP_HOURS: int = 24

    # Debug default veilig uit
    DEBUG: bool = False

    # --- Database & Redis ---
    DATABASE_URL: str = "sqlite:///./aether.db"
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- Storage / S3 ---
    AWS_REGION: str = "eu-west-1"
    S3_BUCKET: Optional[str] = None
    AWS_S3_BUCKET_NAME: Optional[str] = None

    USE_LOCAL_STORAGE: bool = True
    LOCAL_STORAGE_ROOT: str = "./.local_storage"
    S3_BASE_URL: Optional[str] = None

    # Raw AWS creds (optioneel)
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None

    # --- CloudFront ---
    CLOUDFRONT_DOMAIN: Optional[str] = None
    AWS_CLOUDFRONT_BASE_URL: Optional[str] = None

    # --- Upload / presign settings ---
    MAX_UPLOAD_MB: int = 25
    S3_UPLOAD_MAX_MB: int = 25
    S3_UPLOAD_ALLOWED_TYPES: str = "image/jpeg,image/png,application/pdf"
    UPLOAD_DIR: str = "data/uploads"
    OFFERS_DIR: str = "data/offers"
    UPLOAD_MAX_FILES: int = 12

    S3_TEMP_PREFIX: str = "uploads/"
    S3_FINAL_PREFIX: str = "leads/"
    UPLOAD_MAX_BYTES: int = 25 * 1024 * 1024
    UPLOAD_ALLOWED_CONTENT_TYPES: str = ""

    STORAGE_BACKEND: str = "local"
    LOCAL_STORAGE_PATH: str = "data"

    # --- CORS ---
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:8000"

    # --- HubSpot ---
    HUBSPOT_ENABLED: bool = False
    HUBSPOT_TOKEN: Optional[str] = None
    PIPELINE: str = "default"
    STAGE: str = "appointmentscheduled"

    # --- Predictor ---
    PREDICT_MAX_SIDE: int = 1600

    # --- E-mail ---
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM_EMAIL: Optional[str] = None
    SMTP_FROM_NAME: str = "Aether Engine"

    # --- External services ---
    WHATSAPP_API_KEY: Optional[str] = None
    CRM_API_URL: Optional[str] = None
    CRM_API_KEY: Optional[str] = None

    # --- AI / ML services ---
    OPENAI_API_KEY: Optional[str] = None
    VISION_API_URL: Optional[str] = None
    VISION_API_KEY: Optional[str] = None
    PRICING_MODEL_URL: Optional[str] = None

    # --- Frontend ---
    VITE_API_URL: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Helpers
    @property
    def allowed_origins_list(self) -> List[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def s3_upload_allowed_types_list(self) -> List[str]:
        return [t.strip() for t in self.S3_UPLOAD_ALLOWED_TYPES.split(",") if t.strip()]


settings = Settings()
