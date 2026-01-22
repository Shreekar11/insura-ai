import asyncio
from typing import Dict, Any, Optional, List, Union

import httpx
from httpx import TimeoutException, HTTPStatusError

from app.core.exceptions import APIClientError, APITimeoutError
from app.utils.logging import get_logger
from google import genai
from google.genai import types

LOGGER = get_logger(__name__)


class BaseLLMClient:
    """Base client for LLM API interactions.
    
    Handles common logic for HTTP requests, retries, timeout management,
    and error logging.
    """

    def __init__(
        self, 
        api_key: str, 
        base_url: str, 
        timeout: int = 60, 
        max_retries: int = 3,
        retry_delay: int = 2
    ):
        """Initialize the LLM client.
        
        Args:
            api_key: API key for authentication
            base_url: Base URL for the API
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries
            retry_delay: Base delay for exponential backoff
        """
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.logger = LOGGER

    async def call_api(
        self, 
        endpoint: str = "", 
        method: str = "POST",
        payload: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Call the API with retry logic.
        
        Args:
            endpoint: API endpoint (appended to base_url)
            method: HTTP method (POST, GET, etc.)
            payload: JSON payload
            headers: Additional headers
            
        Returns:
            Parsed JSON response
            
        Raises:
            APIClientError: If the API call fails after retries
            APITimeoutError: If the API call times out after retries
        """
        url = f"{self.base_url}{endpoint}" if endpoint else self.base_url
        
        default_headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        if headers:
            default_headers.update(headers)
            
        self.logger.debug(
            f"Calling LLM API: {url}",
            extra={"method": method, "timeout": self.timeout}
        )
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for attempt in range(self.max_retries):
                try:
                    if method.upper() == "GET":
                        response = await client.get(url, headers=default_headers, params=payload)
                    else:
                        response = await client.post(url, headers=default_headers, json=payload)
                        
                    response.raise_for_status()
                    return response.json()
                    
                except HTTPStatusError as e:
                    await self._handle_http_error(e, attempt, url)
                    
                except TimeoutException as e:
                    await self._handle_timeout_error(e, attempt, url)
                    
                except Exception as e:
                    await self._handle_generic_error(e, attempt, url)
                    
        raise APIClientError(f"Failed to call API {url} after {self.max_retries} attempts")

    async def _handle_http_error(self, error: HTTPStatusError, attempt: int, url: str):
        """Handle HTTP status errors."""
        status_code = error.response.status_code
        
        # Log error details
        try:
            error_body = error.response.text
        except:
            error_body = "Could not read response body"
            
        self.logger.warning(
            f"API HTTP error (Attempt {attempt + 1}/{self.max_retries})",
            extra={
                "url": url,
                "status_code": status_code,
                "error_body": error_body[:500]  # Truncate for logs
            }
        )
        
        # Don't retry on client errors (4xx) unless it's rate limiting (429)
        if 400 <= status_code < 500 and status_code != 429:
            raise APIClientError(f"API Client Error {status_code}: {error_body}") from error
            
        if attempt < self.max_retries - 1:
            await self._wait_before_retry(attempt)
        else:
            raise APIClientError(f"API HTTP Error {status_code} after retries") from error

    async def _handle_timeout_error(self, error: TimeoutException, attempt: int, url: str):
        """Handle timeout errors."""
        self.logger.warning(
            f"API Timeout (Attempt {attempt + 1}/{self.max_retries})",
            extra={"url": url}
        )
        
        if attempt < self.max_retries - 1:
            await self._wait_before_retry(attempt)
        else:
            raise APITimeoutError(f"API Timeout after {self.max_retries} attempts") from error

    async def _handle_generic_error(self, error: Exception, attempt: int, url: str):
        """Handle generic errors."""
        self.logger.warning(
            f"API Generic Error (Attempt {attempt + 1}/{self.max_retries})",
            extra={"url": url, "error": str(error)}
        )
        
        if attempt < self.max_retries - 1:
            await self._wait_before_retry(attempt)
        else:
            raise APIClientError(f"API Error: {str(error)}") from error

    async def _wait_before_retry(self, attempt: int):
        """Exponential backoff wait."""
        wait_time = self.retry_delay * (2 ** attempt)
        await asyncio.sleep(wait_time)


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
                # The SDK (google-genai) supports async via `aio`.
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



class OpenRouterClient:
    """Wrapper for OpenRouter API client.
    
    Provides a unified interface compatible with GeminiClient while using
    OpenRouter's API for LLM interactions.
    """

    def __init__(
        self,
        api_key: str,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: int = 60,
        max_retries: int = 5,  # Increased for better reliability with rate limits
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
