# app/config.py
from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# <-- centrale settings vanuit .env
from app.core.settings import settings as env_settings


class Settings(BaseSettings):
    """
    Secondary settings layer used by older aether_engine modules.
    Reads .env via env_settings (the new core settings class).
    """

    # === Algemene app settings ===
    app_env: str = env_settings.APP_ENV  # local | development | production

    # === AWS & S3 ===
    AWS_REGION: str = env_settings.AWS_REGION
    S3_BUCKET: Optional[str] = env_settings.S3_BUCKET
    S3_ENDPOINT_URL: Optional[str] = None
    S3_USE_ACCELERATE: bool = False

    AWS_ACCESS_KEY_ID: Optional[str] = env_settings.AWS_ACCESS_KEY_ID
    AWS_SECRET_ACCESS_KEY: Optional[str] = env_settings.AWS_SECRET_ACCESS_KEY
    AWS_SESSION_TOKEN: Optional[str] = None

    PRESIGN_EXPIRES_SECONDS: int = 900  # 15 min

    # Fallback voor sandbox/tests
    S3_BASE_URL: str = (
        env_settings.S3_BASE_URL or "https://example-bucket.s3.amazonaws.com"
    )

    # === Database ===
    database_url: str = env_settings.DATABASE_URL

    # === Redis ===
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None

    # === Logging ===
    log_level: str = "INFO"
    log_dir: str = "logs"
    log_rotation: str = "1 day"
    log_retention: str = "30 days"

    # === Rate Limiting ===
    rate_limit_quote_create: int = 60
    rate_limit_vision_processing: int = 30
    rate_limit_prediction: int = 100
    rate_limit_global: int = 1000

    # === Metrics ===
    metrics_enabled: bool = True
    metrics_port: int = 9090

    # === Celery / Background ===
    celery_broker_url: str = env_settings.REDIS_URL
    celery_result_backend: str = env_settings.REDIS_URL

    # === Vision ===
    vision_model_path: Optional[str] = None
    vision_confidence_threshold: float = 0.7

    # === HubSpot ===
    hubspot_client_id: Optional[str] = None
    hubspot_client_secret: Optional[str] = None

    # === Pydantic Settings config ===
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Singleton wrapper around Settings + environment-based overrides.
    """
    s = Settings()

    env = env_settings.APP_ENV.lower()

    if env == "production":
        s.log_level = "WARNING"
        s.rate_limit_quote_create = 30
        s.rate_limit_vision_processing = 15
        s.rate_limit_prediction = 50

    elif env == "development":
        s.log_level = "DEBUG"
        s.rate_limit_quote_create = 120
        s.rate_limit_vision_processing = 60
        s.rate_limit_prediction = 200

    return s


# Backwards compatibility: old code imports "settings"
settings = get_settings()
