from pydantic_settings import BaseSettings
from typing import Optional
import os

class Settings(BaseSettings):
    """Applicatie configuratie"""
    
    # Database
    database_url: str = "sqlite:///./levelai.db"
    
    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None
    
    # Logging
    log_level: str = "INFO"
    log_dir: str = "logs"
    log_rotation: str = "1 day"
    log_retention: str = "30 days"
    
    # Rate Limiting
    rate_limit_quote_create: int = 60  # requests per minute
    rate_limit_vision_processing: int = 30  # requests per minute
    rate_limit_prediction: int = 100  # requests per minute
    rate_limit_global: int = 1000  # requests per minute per IP
    
    # Metrics
    metrics_enabled: bool = True
    metrics_port: int = 9090
    
    # Celery
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/0"
    
    # Vision
    vision_model_path: Optional[str] = None
    vision_confidence_threshold: float = 0.7
    
    # HubSpot
    hubspot_client_id: Optional[str] = None
    hubspot_client_secret: Optional[str] = None
    
    class Config:
        env_file = ".env"
        case_sensitive = False

# Global settings instance
settings = Settings()

# Environment-specific overrides
if os.getenv("ENVIRONMENT") == "production":
    settings.log_level = "WARNING"
    settings.rate_limit_quote_create = 30
    settings.rate_limit_vision_processing = 15
    settings.rate_limit_prediction = 50

elif os.getenv("ENVIRONMENT") == "development":
    settings.log_level = "DEBUG"
    settings.rate_limit_quote_create = 120
    settings.rate_limit_vision_processing = 60
    settings.rate_limit_prediction = 200
