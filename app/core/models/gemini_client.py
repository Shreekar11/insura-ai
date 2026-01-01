import asyncio
from typing import Any, Dict, List, Optional, Union

from google import genai
from google.genai import types

from app.utils.logging import get_logger
from app.utils.exceptions import APIClientError

LOGGER = get_logger(__name__)


class GeminiClient:
    """Wrapper for Google Gemini API client."""

    def __init__(
        self,
        api_key: str,
        model: str = "qwen3:8b",
        timeout: int = 60,
        max_retries: int = 3,
    ):
        """Initialize Gemini client.

        Args:
            api_key: Gemini API key
            model: Model name to use
            timeout: Request timeout in seconds (not directly used by SDK but kept for interface consistency)
            max_retries: Maximum retry attempts
        """
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        
        try:
            self.client = genai.Client(api_key=self.api_key)
            LOGGER.info(f"Initialized Gemini client with model {self.model}")
        except Exception as e:
            LOGGER.error(f"Failed to initialize Gemini client: {e}")
            raise APIClientError(f"Failed to initialize Gemini client: {e}")

    async def generate_content(
        self,
        contents: Union[str, List[Union[str, Dict[str, Any]]]],
        system_instruction: Optional[str] = None,
        generation_config: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate content using Gemini model.

        Args:
            contents: Input content (string or list of parts)
            system_instruction: Optional system instruction
            generation_config: Optional generation config (temperature, etc.)

        Returns:
            Generated text response

        Raises:
            APIClientError: If generation fails
        """
        # Default config
        config = types.GenerateContentConfig(
            temperature=0.0,  # Default to deterministic
        )
        
        # Merge provided config
        if generation_config:
            # Map dict to GenerateContentConfig if needed, or pass as kwargs
            # The SDK accepts a config object or kwargs. Let's use the object.
            if "temperature" in generation_config:
                config.temperature = generation_config["temperature"]
            if "max_output_tokens" in generation_config:
                config.max_output_tokens = generation_config["max_output_tokens"]
            if "response_mime_type" in generation_config:
                config.response_mime_type = generation_config["response_mime_type"]
            if "response_schema" in generation_config:
                config.response_schema = generation_config["response_schema"]

        if system_instruction:
            config.system_instruction = system_instruction

        for attempt in range(self.max_retries):
            try:
                # The SDK's generate_content is synchronous by default, but we want async.
                # The V2 SDK (google-genai) supports async via `aio`.
                # However, the user example showed synchronous usage: `client.models.generate_content`.
                # To keep it async compatible with the rest of the app, we should use the async client if available,
                # or run in executor. The `google-genai` package has an async client.
                
                # Re-initializing as async client for this method call would be inefficient.
                # Let's check if we can use the async client from the start.
                # The user example: `client = genai.Client()`.
                # Documentation says: `client.aio.models.generate_content` for async.
                
                response = await self.client.aio.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=config
                )
                
                if not response.text:
                    LOGGER.warning("Empty response from Gemini")
                    return ""
                    
                return response.text

            except Exception as e:
                LOGGER.warning(
                    f"Gemini API error (Attempt {attempt + 1}/{self.max_retries}): {e}"
                )
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    LOGGER.error(f"Gemini generation failed after retries: {e}", exc_info=True)
                    raise APIClientError(f"Gemini generation failed: {e}")
        
        raise APIClientError("Gemini generation failed")
