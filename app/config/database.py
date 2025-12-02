"""Database configuration settings."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Database connection and pool settings."""

    # Database Settings
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/insura_ai"
    database_pool_size: int = 10
    database_max_overflow: int = 20
    database_echo: bool = False  # SQL query logging

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parent.parent.parent / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
