"""Unified LLM client factory and manager.

Provides a unified interface for interacting with different LLM providers
(Gemini, OpenRouter, Ollama, Groq) with automatic provider selection based on configuration.
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Union

from app.core.llm_client import GeminiClient, OpenRouterClient
from app.utils.logging import get_logger
from app.core.exceptions import APIClientError

LOGGER = get_logger(__name__)


class LLMProvider(str, Enum):
    """Supported LLM providers."""
    GEMINI = "gemini"
    OPENROUTER = "openrouter"


class UnifiedLLMClient:
    """Unified LLM client that wraps different providers.
    
    Provides a consistent interface regardless of the underlying provider,
    allowing seamless switching between Gemini, OpenRouter.
    """

    def __init__(
        self,
        provider: Union[str, LLMProvider],
        api_key: str,
        model: str,
        base_url: Optional[str] = None,
        timeout: int = 60,
        max_retries: int = 3,
        fallback_to_gemini: bool = False,
        gemini_api_key: Optional[str] = None,
        gemini_model: Optional[str] = None,
    ):
        """Initialize unified LLM client.

        Args:
            provider: LLM provider to use ("gemini", "openrouter")
            api_key: API key for the primary provider
            model: Model name to use
            base_url: Optional base URL (for OpenRouter)
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
            fallback_to_gemini: If True, fallback to Gemini on primary provider failure
            gemini_api_key: Gemini API key (required if fallback_to_gemini=True)
            gemini_model: Gemini model name (for fallback)
        """
        self.provider = LLMProvider(provider)
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.fallback_to_gemini = fallback_to_gemini
        
        # Initialize primary client
        if self.provider == LLMProvider.GEMINI:
            self.client = GeminiClient(
                api_key=api_key,
                model=model,
                timeout=timeout,
                max_retries=max_retries
            )
            self.fallback_client = None
            LOGGER.info(f"Initialized unified LLM with Gemini provider (model: {model})")
            
        elif self.provider == LLMProvider.OPENROUTER:
            self.client = OpenRouterClient(
                api_key=api_key,
                model=model,
                base_url=base_url,
                timeout=timeout,
                max_retries=max_retries
            )
            
            # Initialize fallback client if enabled
            if fallback_to_gemini:
                if not gemini_api_key:
                    raise ValueError("gemini_api_key required when fallback_to_gemini=True")
                self.fallback_client = GeminiClient(
                    api_key=gemini_api_key,
                    model=gemini_model or "gemini-2.0-flash",
                    timeout=timeout,
                    max_retries=max_retries
                )
                LOGGER.info(
                    f"Initialized unified LLM with OpenRouter provider (model: {model}) "
                    f"and Gemini fallback (model: {gemini_model})"
                )
            else:
                self.fallback_client = None
                LOGGER.info(f"Initialized unified LLM with OpenRouter provider (model: {model})")
                
        elif self.provider == LLMProvider.GEMINI:
            self.client = GeminiClient(
                api_key=api_key,
                model=model,
                base_url=base_url,
                timeout=timeout,
                max_retries=max_retries
            )
            
            # Initialize fallback client if enabled
            if fallback_to_gemini:
                if not gemini_api_key:
                    raise ValueError("gemini_api_key required when fallback_to_gemini=True")
                self.fallback_client = GeminiClient(
                    api_key=gemini_api_key,
                    model=gemini_model or "gemini-2.0-flash",
                    timeout=timeout,
                    max_retries=max_retries
                )
                LOGGER.info(
                    f"Initialized unified LLM with Gemini provider (model: {model}) "
                    f"and Gemini fallback (model: {gemini_model})"
                )
            else:
                self.fallback_client = None
                LOGGER.info(f"Initialized unified LLM with Gemini provider (model: {model})")
        else:
            raise ValueError(f"Unsupported provider: {provider}")

    async def generate_content(
        self,
        contents: Union[str, List[Union[str, Dict[str, Any]]]],
        system_instruction: Optional[str] = None,
        generation_config: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate content using the configured LLM provider.

        Args:
            contents: Input content (string or list of parts)
            system_instruction: Optional system instruction
            generation_config: Optional generation config (temperature, etc.)

        Returns:
            Generated text response

        Raises:
            APIClientError: If generation fails
        """
        try:
            # Try primary client
            return await self.client.generate_content(
                contents=contents,
                system_instruction=system_instruction,
                generation_config=generation_config
            )
        except Exception as e:
            # Try fallback if enabled
            if self.fallback_client:
                LOGGER.warning(
                    f"Primary provider ({self.provider}) failed, attempting Gemini fallback: {e}"
                )
                try:
                    return await self.fallback_client.generate_content(
                        contents=contents,
                        system_instruction=system_instruction,
                        generation_config=generation_config
                    )
                except Exception as fallback_error:
                    LOGGER.error(f"Fallback to Gemini also failed: {fallback_error}")
                    raise APIClientError(
                        f"Both primary ({self.provider}) and fallback (Gemini) failed"
                    ) from fallback_error
            else:
                # No fallback, re-raise original error
                raise


def create_llm_client(
    provider: Union[str, LLMProvider],
    api_key: str = "",
    model: str = "gemini-2.0-flash",
    base_url: Optional[str] = None,
    timeout: int = 60,
    max_retries: int = 3,
    fallback_to_gemini: bool = False,
    gemini_api_key: Optional[str] = None,
    gemini_model: Optional[str] = None,
) -> UnifiedLLMClient:
    """Factory function to create a unified LLM client.

    Args:
        provider: LLM provider to use ("gemini", "openrouter")
        api_key: API key for the primary provider
        model: Model name to use
        base_url: Optional base URL (for OpenRouter)
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts
        fallback_to_gemini: If True, fallback to Gemini on primary provider failure
        gemini_api_key: Gemini API key (required if fallback_to_gemini=True)
        gemini_model: Gemini model name (for fallback)

    Returns:
        UnifiedLLMClient instance
    """
    return UnifiedLLMClient(
        provider=provider,
        api_key=api_key,
        model=model,
        base_url=base_url,
        timeout=timeout,
        max_retries=max_retries,
        fallback_to_gemini=fallback_to_gemini,
        gemini_api_key=gemini_api_key,
        gemini_model=gemini_model,
    )


def create_llm_client_from_settings(
    provider: str,
    gemini_api_key: str = "",
    gemini_model: Optional[str] = None,
    openrouter_api_key: Optional[str] = None,
    openrouter_api_url: Optional[str] = None,
    openrouter_model: Optional[str] = None,
    timeout: int = 90,
    max_retries: int = 3,
    enable_fallback: bool = False,
) -> UnifiedLLMClient:
    """Create a unified LLM client from configuration settings.
    
    This is a convenience function that automatically selects the appropriate
    API key, model, and base URL based on the provider setting.
    
    Args:
        provider: LLM provider to use ("gemini", "openrouter", "ollama", or "groq")
        gemini_api_key: Gemini API key (required if provider="gemini")
        gemini_model: Gemini model name
        openrouter_api_key: OpenRouter API key (required if provider="openrouter")
        openrouter_api_url: OpenRouter API URL
        openrouter_model: OpenRouter model name
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts
        enable_fallback: If True, enable Gemini fallback for non-Gemini providers
        
    Returns:
        UnifiedLLMClient instance configured with the specified provider
        
    Raises:
        ValueError: If required API key is missing for the selected provider
    """
    provider_enum = LLMProvider(provider.lower())
    
    if provider_enum == LLMProvider.GEMINI:
        if not gemini_api_key or (isinstance(gemini_api_key, str) and not gemini_api_key.strip()):
            raise ValueError(
                "gemini_api_key required when provider='gemini'. "
                "Please set GEMINI_API_KEY environment variable."
            )
        api_key = gemini_api_key.strip() if isinstance(gemini_api_key, str) else gemini_api_key
        return UnifiedLLMClient(
            provider=provider_enum,
            api_key=api_key,
            model=gemini_model,
            timeout=timeout,
            max_retries=max_retries,
            fallback_to_gemini=False,
        )
    
    elif provider_enum == LLMProvider.OPENROUTER:
        if not openrouter_api_key or (isinstance(openrouter_api_key, str) and not openrouter_api_key.strip()):
            raise ValueError(
                "openrouter_api_key required when provider='openrouter'. "
                "Please set OPENROUTER_API_KEY environment variable."
            )
        api_key = openrouter_api_key.strip() if isinstance(openrouter_api_key, str) else openrouter_api_key
        fallback_gemini_key = None
        if enable_fallback and gemini_api_key:
            if isinstance(gemini_api_key, str) and gemini_api_key.strip():
                fallback_gemini_key = gemini_api_key.strip()
            elif not isinstance(gemini_api_key, str):
                fallback_gemini_key = gemini_api_key
        
        return UnifiedLLMClient(
            provider=provider_enum,
            api_key=api_key,
            model=openrouter_model,
            base_url=openrouter_api_url,
            timeout=timeout,
            max_retries=max_retries,
            fallback_to_gemini=enable_fallback,
            gemini_api_key=fallback_gemini_key,
            gemini_model=gemini_model if enable_fallback else None,
        )
    
    else:
        raise ValueError(f"Unsupported provider: {provider}")
