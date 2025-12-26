"""Ollama LLM client implementation."""

import asyncio
from typing import Any, Dict, List, Optional, Union

import ollama

from app.utils.logging import get_logger
from app.utils.exceptions import APIClientError

LOGGER = get_logger(__name__)


class OllamaClient:
    """Wrapper for Ollama API client.
    
    Provides a unified interface compatible with GeminiClient and OpenRouterClient
    while using Ollama's local API for LLM interactions.
    """

    def __init__(
        self,
        api_key: str = "",  # Ollama doesn't require API key for local usage
        model: str = "deepseek-r1:7b",
        base_url: str = "http://localhost:11434",
        timeout: int = 60,
        max_retries: int = 3,
    ):
        """Initialize Ollama client.

        Args:
            api_key: API key (not used for local Ollama, kept for interface consistency)
            model: Model name to use (e.g., "deepseek-r1:7b")
            base_url: Ollama API base URL (default: http://localhost:11434)
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
        """
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = 2  # Base delay for exponential backoff
        
        # Initialize Ollama client
        try:
            # Normalize base_url: remove protocol and any trailing paths
            # Ollama client expects just hostname:port
            normalized_host = base_url
            if normalized_host.startswith("http://"):
                normalized_host = normalized_host[7:]
            elif normalized_host.startswith("https://"):
                normalized_host = normalized_host[8:]
            # Remove any trailing paths (like /v1, /api, etc.)
            if "/" in normalized_host:
                normalized_host = normalized_host.split("/")[0]
            
            # Set the base URL for the Ollama client with timeout
            self.client = ollama.AsyncClient(host=normalized_host, timeout=timeout)
            LOGGER.info(f"Initialized Ollama client with model {self.model} at {normalized_host} (timeout: {timeout}s)")
        except Exception as e:
            LOGGER.error(f"Failed to initialize Ollama client: {e}")
            raise APIClientError(f"Failed to initialize Ollama client: {e}")

    async def generate_content(
        self,
        contents: Union[str, List[Union[str, Dict[str, Any]]]],
        system_instruction: Optional[str] = None,
        generation_config: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate content using Ollama model.

        Args:
            contents: Input content (string or list of parts)
            system_instruction: Optional system instruction
            generation_config: Optional generation config (temperature, etc.)

        Returns:
            Generated text response

        Raises:
            APIClientError: If generation fails
        """
        # Build messages array for Ollama
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
        
        # Build options dict for Ollama
        options = {}
        if generation_config:
            if "temperature" in generation_config:
                options["temperature"] = generation_config["temperature"]
            if "max_output_tokens" in generation_config:
                options["num_predict"] = generation_config["max_output_tokens"]
        else:
            # Default to deterministic
            options["temperature"] = 0.0
        
        # Check if JSON format is requested
        format_param = None
        if generation_config and generation_config.get("response_mime_type") == "application/json":
            format_param = "json"
            # Add JSON instruction to system message
            json_instruction = "\n\nIMPORTANT: Respond with valid JSON only. Do not include markdown code blocks (```json or ```), no explanatory text, and no text outside the JSON object."
            # Find existing system message or create new one
            system_msg_found = False
            for msg in messages:
                if msg.get("role") == "system":
                    msg["content"] += json_instruction
                    system_msg_found = True
                    break
            if not system_msg_found:
                messages.insert(0, {
                    "role": "system",
                    "content": "Respond with valid JSON only. Do not include markdown code blocks (```json or ```), no explanatory text, and no text outside the JSON object."
                })
        
        for attempt in range(self.max_retries):
            try:
                LOGGER.info(
                    f"Ollama API call attempt {attempt + 1}/{self.max_retries}",
                    extra={
                        "model": self.model,
                        "message_count": len(messages),
                        "format": format_param,
                        "options": options,
                    }
                )
                
                # Call Ollama API
                # Pass options as keyword argument if provided
                chat_kwargs = {
                    "model": self.model,
                    "messages": messages,
                }
                if options:
                    chat_kwargs["options"] = options
                
                # Try with JSON format first if requested
                if format_param:
                    chat_kwargs["format"] = format_param
                
                LOGGER.info("Calling Ollama API...")
                
                # Add timeout wrapper
                try:
                    response = await asyncio.wait_for(
                        self.client.chat(**chat_kwargs),
                        timeout=self.timeout
                    )
                    LOGGER.info("Ollama API call completed successfully")
                except asyncio.TimeoutError:
                    LOGGER.error(f"Ollama API call timed out after {self.timeout}s")
                    raise APIClientError(f"Ollama API call timed out after {self.timeout}s")
                
                # Extract text from response
                if hasattr(response, "message") and response.message:
                    content = response.message.content
                    
                    if not content or not content.strip():
                        # If JSON format was requested and we got empty response,
                        # try once without format constraint on last attempt
                        if format_param and attempt == self.max_retries - 1:
                            LOGGER.warning(
                                "Empty response with JSON format, retrying without format constraint"
                            )
                            chat_kwargs_no_format = {
                                "model": self.model,
                                "messages": messages,
                            }
                            if options:
                                chat_kwargs_no_format["options"] = options
                            response = await self.client.chat(**chat_kwargs_no_format)
                            if hasattr(response, "message") and response.message:
                                content = response.message.content
                        
                        if not content or not content.strip():
                            LOGGER.warning(
                                f"Empty response from Ollama (Attempt {attempt + 1}/{self.max_retries})",
                                extra={"model": self.model, "format": format_param}
                            )
                            if attempt < self.max_retries - 1:
                                continue
                            return ""
                    
                    # Log response preview for debugging
                    LOGGER.info(
                        f"Ollama response received successfully",
                        extra={
                            "model": self.model,
                            "content_preview": content[:200] if len(content) > 200 else content,
                            "content_length": len(content)
                        }
                    )
                    
                    return content
                else:
                    LOGGER.error(
                        f"Unexpected Ollama response format: {response}",
                        extra={"response_type": type(response).__name__}
                    )
                    raise APIClientError("Invalid response format from Ollama")
                    
            except Exception as e:
                LOGGER.warning(
                    f"Ollama API error (Attempt {attempt + 1}/{self.max_retries}): {e}"
                )
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    LOGGER.error(f"Ollama generation failed after retries: {e}", exc_info=True)
                    raise APIClientError(f"Ollama generation failed: {e}")
        
        raise APIClientError("Ollama generation failed")

