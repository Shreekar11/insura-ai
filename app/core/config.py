"""Application configuration."""

from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.utils.logging import get_logger

LOGGER = get_logger(__name__)

# Find .env file - check multiple possible locations
def find_env_file() -> Optional[Path]:
    """Find .env file in multiple possible locations."""
    import os
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    possible_paths = [
        os.path.join(current_dir, ".env"),
        os.path.join(os.path.dirname(current_dir), ".env"),
        os.path.join(os.path.dirname(os.path.dirname(current_dir)), ".env"),
    ]
    
    for path_str in possible_paths:
        if os.path.exists(path_str):
            path = Path(path_str)
            LOGGER.info(f"Found .env file at: {path}")
            return path
    
    LOGGER.warning("No .env file found in expected locations")
    return None


ENV_FILE = find_env_file()


class DatabaseSettings(BaseSettings):
    """Database connection and pool settings."""
    url: str = Field(default="postgresql+asyncpg://insura:insura@localhost:5432/insura_temp", validation_alias="DATABASE_URL")
    pool_size: int = Field(default=10, validation_alias="DATABASE_POOL_SIZE")
    max_overflow: int = Field(default=20, validation_alias="DATABASE_MAX_OVERFLOW")
    echo: bool = Field(default=False, validation_alias="DATABASE_ECHO")
    
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE) if ENV_FILE else None,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_prefix="",  # No prefix for nested settings
    )


class LLMSettings(BaseSettings):
    """LLM provider and OCR service settings."""

    provider: str = Field(default="openrouter", validation_alias="LLM_PROVIDER")
    
    gemini_api_key: str = Field(default="", validation_alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.0-flash", validation_alias="GEMINI_MODEL")
    
    openrouter_api_key: str = Field(default="", validation_alias="OPENROUTER_API_KEY")
    openrouter_api_url: str = Field(default="https://openrouter.ai/api/v1/chat/completions", validation_alias="OPENROUTER_API_URL")
    openrouter_model: str = Field(default="openai/gpt-4o-mini", validation_alias="OPENROUTER_MODEL")
    
    enable_fallback: bool = Field(default=False, validation_alias="ENABLE_LLM_FALLBACK")

    # Chunking
    chunk_max_tokens: int = Field(default=1500, validation_alias="CHUNK_MAX_TOKENS")
    chunk_min_tokens: int = Field(default=300, validation_alias="CHUNK_MIN_TOKENS")
    chunk_overlap_tokens: int = Field(default=50, validation_alias="CHUNK_OVERLAP_TOKENS")
    enable_section_chunking: bool = Field(default=True, validation_alias="ENABLE_SECTION_CHUNKING")
    
    # Super-chunk limits (for LLM token limits)
    max_tokens_per_super_chunk: int = Field(default=6000, validation_alias="MAX_TOKENS_PER_SUPER_CHUNK")
    max_tokens_per_batch: int = Field(default=12000, validation_alias="MAX_TOKENS_PER_BATCH")

    # Batch Processing
    batch_size: int = Field(default=3, validation_alias="BATCH_SIZE")
    max_batch_retries: int = Field(default=2, validation_alias="MAX_BATCH_RETRIES")
    batch_timeout_seconds: int = Field(default=90, validation_alias="BATCH_TIMEOUT_SECONDS")
    
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE) if ENV_FILE else None,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_prefix="",  # No prefix for nested settings
    )

    def model_post_init(self, __context) -> None:
        """Log settings after initialization."""
        LOGGER.info(f"LLM Provider: {self.provider}")
        if self.provider == "gemini":
            LOGGER.info(f"Gemini API Key present: {bool(self.gemini_api_key)}")
            LOGGER.info(f"Gemini API Key length: {len(self.gemini_api_key)}")
        elif self.provider == "openrouter":
            LOGGER.info(f"OpenRouter API Key present: {bool(self.openrouter_api_key)}")
            LOGGER.info(f"OpenRouter API Key length: {len(self.openrouter_api_key)}")
        else:
            LOGGER.error("Invalid LLM provider specified!")

class TemporalSettings(BaseSettings):
    """Temporal connection and workflow settings."""
    host: str = Field(default="localhost", validation_alias="TEMPORAL_HOST")
    port: int = Field(default=7233, validation_alias="TEMPORAL_PORT")
    namespace: str = Field(default="default", validation_alias="TEMPORAL_NAMESPACE")
    task_queue: str = Field(default="documents-queue", validation_alias="TEMPORAL_TASK_QUEUE")
    
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE) if ENV_FILE else None,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_prefix="",  # No prefix for nested settings
    )


class Neo4jSettings(BaseSettings):
    """Neo4j connection and graph settings."""
    host: str = Field(default="localhost", validation_alias="NEO4J_HOST")
    port: int = Field(default=7687, validation_alias="NEO4J_PORT")
    username: str = Field(default="neo4j", validation_alias="NEO4J_USERNAME")
    password: str = Field(default="password", validation_alias="NEO4J_PASSWORD")
    database: str = Field(default="neo4j", validation_alias="NEO4J_DATABASE")

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE) if ENV_FILE else None,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_prefix="",
    )


class SupabaseSettings(BaseSettings):
    """Supabase authentication settings."""
    url: str = Field(default="", validation_alias="SUPABASE_URL")
    anon_key: str = Field(default="", validation_alias="SUPABASE_ANON_KEY")
    service_role_key: str = Field(default="", validation_alias="SUPABASE_SERVICE_ROLE_KEY")
    jwt_secret: str = Field(default="", validation_alias="SUPABASE_JWT_SECRET")
    jwks_cache_ttl: int = Field(default=3600, validation_alias="SUPABASE_JWKS_CACHE_TTL")  # 1 hour

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE) if ENV_FILE else None,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_prefix="",
    )


class Settings(BaseSettings):
    """Unified application settings with nested models."""

    # Application Settings
    app_name: str = Field(default="Insura AI", validation_alias="APP_NAME")
    app_version: str = "0.1.0"
    environment: str = Field(default="development", validation_alias="ENVIRONMENT")
    debug: bool = Field(default=True, validation_alias="DEBUG")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")

    # API Settings
    api_v1_prefix: str = "/api/v1"
    host: str = Field(default="0.0.0.0", validation_alias="HOST")
    port: int = Field(default=8000, validation_alias="PORT")

    # Timeout Settings
    ocr_timeout: int = 120
    http_timeout: int = 60

    # Rate Limiting
    max_retries: int = 3
    retry_delay: int = 2

    # Nested Settings - Initialize with env file explicitly
    db: DatabaseSettings = Field(default_factory=lambda: DatabaseSettings())
    llm: LLMSettings = Field(default_factory=lambda: LLMSettings())
    temporal: TemporalSettings = Field(default_factory=lambda: TemporalSettings())
    neo4j: Neo4jSettings = Field(default_factory=lambda: Neo4jSettings())
    supabase: SupabaseSettings = Field(default_factory=lambda: SupabaseSettings())

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE) if ENV_FILE else None,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Backward compatibility properties
    @property
    def database_url(self) -> str: 
        return self.db.url
    
    @property
    def database_pool_size(self) -> int: 
        return self.db.pool_size
    
    @property
    def database_max_overflow(self) -> int: 
        return self.db.max_overflow
    
    @property
    def database_echo(self) -> bool: 
        return self.db.echo

    @property
    def gemini_api_key(self) -> str: 
        return self.llm.gemini_api_key
    
    @property
    def gemini_model(self) -> str: 
        return self.llm.gemini_model
    
    @property
    def llm_provider(self) -> str: 
        return self.llm.provider
    
    @property
    def openrouter_api_key(self) -> str: 
        return self.llm.openrouter_api_key
    
    @property
    def openrouter_api_url(self) -> str: 
        return self.llm.openrouter_api_url
    
    @property
    def openrouter_model(self) -> str: 
        return self.llm.openrouter_model
    
    @property
    def enable_llm_fallback(self) -> bool: 
        return self.llm.enable_fallback
    
    @property
    def chunk_max_tokens(self) -> int: 
        return self.llm.chunk_max_tokens
    
    @property
    def chunk_overlap_tokens(self) -> int: 
        return self.llm.chunk_overlap_tokens
    
    @property
    def enable_section_chunking(self) -> bool: 
        return self.llm.enable_section_chunking
    
    @property
    def chunk_min_tokens(self) -> int:
        return self.llm.chunk_min_tokens
    
    @property
    def batch_size(self) -> int: 
        return self.llm.batch_size
    
    @property
    def max_batch_retries(self) -> int: 
        return self.llm.max_batch_retries
    
    @property
    def batch_timeout_seconds(self) -> int: 
        return self.llm.batch_timeout_seconds
    
    @property
    def max_tokens_per_super_chunk(self) -> int:
        return self.llm.max_tokens_per_super_chunk
    
    @property
    def max_tokens_per_batch(self) -> int:
        return self.llm.max_tokens_per_batch

    @property
    def temporal_host(self) -> str: 
        return self.temporal.host
    
    @property
    def temporal_port(self) -> int: 
        return self.temporal.port
    
    @property
    def temporal_namespace(self) -> str: 
        return self.temporal.namespace
    
    @property
    def temporal_task_queue(self) -> str:
        return self.temporal.task_queue

    @property
    def supabase_url(self) -> str:
        return self.supabase.url

    @property
    def supabase_anon_key(self) -> str:
        return self.supabase.anon_key

    @property
    def supabase_service_role_key(self) -> str:
        return self.supabase.service_role_key

    @property
    def supabase_jwt_secret(self) -> str:
        return self.supabase.jwt_secret


    @property
    def supabase_jwks_cache_ttl(self) -> int:
        return self.supabase.jwks_cache_ttl


# Initialize settings
settings = Settings()

# Log initialization for debugging
LOGGER.info(f"Settings initialized with environment: {settings.environment}")
LOGGER.info(f"LLM Provider: {settings.llm_provider}")
if settings.llm_provider == "gemini":
    LOGGER.info(f"Gemini API Key loaded: {bool(settings.gemini_api_key)}")
    LOGGER.info(f"Gemini API Key length: {len(settings.gemini_api_key)}")
else:
    LOGGER.info(f"OpenRouter API Key loaded: {bool(settings.openrouter_api_key)}")
    LOGGER.info(f"OpenRouter API Key length: {len(settings.openrouter_api_key)}")
