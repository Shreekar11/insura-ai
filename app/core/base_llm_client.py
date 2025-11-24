import asyncio
import json
from typing import Dict, Any, Optional, List, Union

import httpx
from httpx import TimeoutException, HTTPStatusError

from app.core.exceptions import APIClientError, APITimeoutError
from app.utils.logging import get_logger

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
