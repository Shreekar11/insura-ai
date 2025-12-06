"""OpenRouter LLM client implementation."""

import asyncio
from typing import Any, Dict, List, Optional, Union

from app.core.base_llm_client import BaseLLMClient
from app.utils.logging import get_logger
from app.utils.exceptions import APIClientError

LOGGER = get_logger(__name__)


class OpenRouterClient:
    """Wrapper for OpenRouter API client.
    
    Provides a unified interface compatible with GeminiClient while using
    OpenRouter's API for LLM interactions.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "openai/gpt-oss-20b:free",
        base_url: str = "https://openrouter.ai/api/v1/chat/completions",
        timeout: int = 60,
        max_retries: int = 3,
    ):
        """Initialize OpenRouter client.

        Args:
            api_key: OpenRouter API key
            model: Model name to use (e.g., "openai/gpt-oss-20b:free")
            base_url: OpenRouter API base URL
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
        """
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        
        # Initialize base LLM client for HTTP operations
        self.client = BaseLLMClient(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries
        )
        
        LOGGER.info(f"Initialized OpenRouter client with model {self.model}")

    async def generate_content(
        self,
        contents: Union[str, List[Union[str, Dict[str, Any]]]],
        system_instruction: Optional[str] = None,
        generation_config: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate content using OpenRouter model.

        Args:
            contents: Input content (string or list of parts)
            system_instruction: Optional system instruction
            generation_config: Optional generation config (temperature, etc.)

        Returns:
            Generated text response

        Raises:
            APIClientError: If generation fails
        """
        # Build messages array for OpenRouter
        messages = []
        
        # Add system instruction if provided
        if system_instruction:
            messages.append({
                "role": "system",
                "content": system_instruction
            })
        
        # Add user content
        if isinstance(contents, str):
            messages.append({
                "role": "user",
                "content": contents
            })
        elif isinstance(contents, list):
            # Handle list of content parts
            user_content = ""
            for part in contents:
                if isinstance(part, str):
                    user_content += part
                elif isinstance(part, dict) and "text" in part:
                    user_content += part["text"]
            messages.append({
                "role": "user",
                "content": user_content
            })
        
        # Build request payload
        payload = {
            "model": self.model,
            "messages": messages,
        }
        
        # Add generation config if provided
        if generation_config:
            if "temperature" in generation_config:
                payload["temperature"] = generation_config["temperature"]
            if "max_output_tokens" in generation_config:
                payload["max_tokens"] = generation_config["max_output_tokens"]
            if "response_mime_type" in generation_config:
                # OpenRouter doesn't directly support response_mime_type
                # but we can add it to the system instruction
                if generation_config["response_mime_type"] == "application/json":
                    if system_instruction:
                        messages[0]["content"] += "\n\nIMPORTANT: Respond with valid JSON only."
                    else:
                        messages.insert(0, {
                            "role": "system",
                            "content": "Respond with valid JSON only."
                        })
        else:
            # Default to deterministic
            payload["temperature"] = 0.0
        
        try:
            # Call OpenRouter API
            response = await self.client.call_api(
                endpoint="",  # Base URL already includes the endpoint
                method="POST",
                payload=payload
            )
            
            # Extract text from response
            if "choices" in response and len(response["choices"]) > 0:
                message = response["choices"][0].get("message", {})
                content = message.get("content", "")
                
                if not content:
                    LOGGER.warning("Empty response from OpenRouter")
                    return ""
                
                return content
            else:
                LOGGER.error(f"Unexpected OpenRouter response format: {response}")
                raise APIClientError("Invalid response format from OpenRouter")
                
        except Exception as e:
            LOGGER.error(f"OpenRouter generation failed: {e}", exc_info=True)
            raise APIClientError(f"OpenRouter generation failed: {e}")
