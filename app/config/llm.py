"""LLM and OCR service configuration settings."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    """LLM provider and OCR service settings."""

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

    # Batch Processing Configuration
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

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parent.parent.parent / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
