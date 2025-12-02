"""Core application settings."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class CoreSettings(BaseSettings):
    """Core application settings."""

    # Application Settings
    app_name: str = "Insura AI - AI-powered workspace and assistant designed specifically for insurance operations"
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = True
    log_level: str = "INFO"

    # API Settings
    api_v1_prefix: str = "/api/v1"
    host: str = "0.0.0.0"
    port: int = 8000

    # Timeout Settings (in seconds)
    ocr_timeout: int = 120
    http_timeout: int = 60

    # Rate Limiting
    max_retries: int = 3
    retry_delay: int = 2

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parent.parent.parent / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
