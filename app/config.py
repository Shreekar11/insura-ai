"""Application configuration management."""

from pathlib import Path

from pydantic import Field
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

    # Gemini API Configuration
    gemini_api_key: str = Field(..., description="Gemini API key")
    gemini_model: str = Field(
        default="gemini-2.0-flash",
        description="Gemini model name"
    )

    # LLM Provider Configuration
    llm_provider: str = Field(
        default="gemini",
        description="LLM provider to use: 'gemini' or 'openrouter'"
    )
    
    # OpenRouter API Configuration
    openrouter_api_key: str = Field(
        default="",
        description="OpenRouter API key (required if llm_provider='openrouter')"
    )
    openrouter_api_url: str = Field(
        default="https://openrouter.ai/api/v1/chat/completions",
        description="OpenRouter API base URL"
    )
    openrouter_model: str = Field(
        default="google/gemini-2.0-flash-001",
        description="OpenRouter model name"
    )
    
    # LLM Fallback Configuration
    enable_llm_fallback: bool = Field(
        default=False,
        description="Enable automatic fallback to Gemini if OpenRouter fails"
    )

    # Chunking Configuration
    chunk_max_tokens: int = Field(
        default=1500,
        description="Maximum tokens per chunk for LLM processing"
    )
    chunk_overlap_tokens: int = Field(
        default=50,
        description="Number of tokens to overlap between chunks"
    )
    enable_section_chunking: bool = Field(
        default=True,
        description="Enable section-aware chunking for insurance documents"
    )
    enable_chunking: bool = Field(
        default=True,
        description="Enable automatic chunking for large documents"
    )

    # Batch Processing Configuration (Pipeline Optimization)
    enable_unified_batch_processing: bool = Field(
        default=True,
        description="Enable unified batch extraction pipeline (reduces LLM calls by 75-85%)"
    )
    batch_size: int = Field(
        default=3,
        description="Number of chunks to process per batch in unified extraction"
    )
    max_batch_retries: int = Field(
        default=2,
        description="Maximum retries for failed batch processing"
    )
    batch_timeout_seconds: int = Field(
        default=90,
        description="Timeout for batch LLM calls in seconds"
    )
    enable_parallel_quality_check: bool = Field(
        default=False,
        description="Run both old and new pipelines for quality comparison (testing only)"
    )
    quality_comparison_sample_rate: float = Field(
        default=0.1,
        description="Percentage of documents to run through both pipelines (0.0-1.0)"
    )


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

