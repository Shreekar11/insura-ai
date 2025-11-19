"""Application configuration management."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application Settings
    app_name: str = "Insurance AI - OCR Service"
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = True
    log_level: str = "INFO"

    # API Settings
    api_v1_prefix: str = "/api/v1"
    host: str = "0.0.0.0"
    port: int = 8000

    # OCR Service Settings
    mistral_api_key: str
    mistral_api_url: str = "https://api.mistral.ai/v1/ocr"
    mistral_model: str = "mistral-ocr-latest"

    openrouter_api_key: str
    openrouter_api_url: str = "https://openrouter.ai/api/v1/chat/completions"
    openrouter_model: str = "nvidia/nemotron-nano-12b-v2-vl:free"

    # Timeout Settings (in seconds)
    ocr_timeout: int = 120
    http_timeout: int = 60

    # Rate Limiting
    max_retries: int = 3
    retry_delay: int = 2

    # Database Settings
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/insura_ai"
    database_pool_size: int = 10
    database_max_overflow: int = 20
    database_echo: bool = False  # SQL query logging

    # Temporal Settings
    temporal_host: str = "localhost"
    temporal_port: int = 7233
    temporal_namespace: str = "default"
    temporal_task_queue: str = "insura-ai-queue"

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parent.parent / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


def get_settings() -> Settings:
    """Get application settings instance.

    Returns:
        Settings: Application settings loaded from environment
    """
    return Settings()


# Global settings instance
settings = get_settings()

