"""OCR repository for handling external API interactions and HTTP operations."""

import time
from typing import Dict, Any, List

import httpx

from app.models.page_data import PageData
from app.utils.exceptions import (
    OCRExtractionError,
    OCRTimeoutError,
    InvalidDocumentError,
    APIClientError,
)
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class OCRRepository:
    """Repository for OCR-related external operations.
    
    This class handles all external HTTP interactions including:
    - Document downloads
    - Mistral API calls
    - Retry logic
    - Error handling for network operations
    """

    def __init__(
        self,
        api_key: str,
        api_url: str,
        timeout: int = 120,
        max_retries: int = 3,
        retry_delay: int = 2,
    ):
        """Initialize OCR repository.

        Args:
            api_key: Mistral API key
            api_url: Mistral API endpoint URL
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
            retry_delay: Delay between retries in seconds
        """
        self.api_key = api_key
        self.api_url = api_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        LOGGER.info(
            "Initialized OCR repository",
            extra={
                "api_url": self.api_url,
                "timeout": self.timeout,
                "max_retries": self.max_retries,
            },
        )

    async def download_document(self, document_url: str) -> bytes:
        """Download document from URL.

        Args:
            document_url: URL of the document to download

        Returns:
            bytes: Document content

        Raises:
            InvalidDocumentError: If document cannot be downloaded
        """
        LOGGER.debug("Downloading document", extra={"document_url": document_url})

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(document_url)
                response.raise_for_status()

                content_type = response.headers.get("content-type", "")
                if "pdf" not in content_type.lower() and "image" not in content_type.lower():
                    LOGGER.warning(
                        "Unexpected content type",
                        extra={"content_type": content_type, "document_url": document_url},
                    )

                LOGGER.debug(
                    "Document downloaded successfully",
                    extra={
                        "document_url": document_url,
                        "content_type": content_type,
                        "size_bytes": len(response.content),
                    },
                )

                return response.content

            except httpx.HTTPStatusError as e:
                LOGGER.error(
                    "Failed to download document - HTTP error",
                    exc_info=True,
                    extra={"document_url": document_url, "status_code": e.response.status_code},
                )
                raise InvalidDocumentError(
                    f"Failed to download document: HTTP {e.response.status_code}"
                ) from e

            except Exception as e:
                LOGGER.error(
                    "Failed to download document",
                    exc_info=True,
                    extra={"document_url": document_url, "error": str(e)},
                )
                raise InvalidDocumentError(f"Failed to download document: {str(e)}") from e

    async def call_mistral_ocr_api(
        self,
        document_url: str,
        model: str,
    ) -> List[PageData]:
        """Call Mistral OCR API to extract text from document.

        Args:
            document_url: Original document URL
            model: Model name to use

        Returns:
            List[PageData]: List of page-specific data with text and metadata

        Raises:
            APIClientError: If API call fails
            OCRTimeoutError: If API call times out
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": model,
            "document": {
                "type": "document_url",
                "document_url": document_url,
            },
            "include_image_base64": False,
        }

        LOGGER.debug(
            "Calling Mistral OCR API",
            extra={"model": model, "document_url": document_url},
        )

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for attempt in range(self.max_retries):
                try:
                    response = await client.post(self.api_url, json=payload, headers=headers)
                    response.raise_for_status()

                    result = response.json()
                    
                    # Extract page-specific data from OCR API response
                    pages = result.get("pages", [])
                    
                    # Create PageData objects for each page
                    page_data_list = []
                    for idx, page in enumerate(pages):
                        # Get page number (1-indexed)
                        page_number = idx + 1
                        
                        # Extract text and markdown
                        markdown = page.get("markdown", "")
                        text = page.get("text", "")
                        
                        # Use markdown if available, otherwise use text
                        if not markdown and not text:
                            LOGGER.warning(
                                f"Page {page_number} has no text or markdown content",
                                extra={"document_url": document_url, "page_number": page_number}
                            )
                            continue
                        
                        # Create PageData object
                        page_data = PageData(
                            page_number=page_number,
                            text=text or markdown,  # Fallback to markdown if text is empty
                            markdown=markdown if markdown else None,
                            metadata={
                                "source": "mistral_ocr",
                                "model": model,
                            }
                        )
                        page_data_list.append(page_data)

                    LOGGER.debug(
                        "Mistral OCR API call successful",
                        extra={
                            "document_url": document_url,
                            "attempt": attempt + 1,
                            "pages_processed": len(page_data_list),
                            "total_text_length": sum(len(p) for p in page_data_list),
                        },
                    )

                    return page_data_list

                except httpx.HTTPStatusError as e:
                    await self._handle_http_error(e, attempt, document_url)

                except httpx.TimeoutException as e:
                    await self._handle_timeout_error(e, attempt, document_url)

                except Exception as e:
                    await self._handle_generic_error(e, attempt, document_url)

        raise APIClientError("Failed to extract text after all retry attempts")

    async def _handle_http_error(
        self,
        error: httpx.HTTPStatusError,
        attempt: int,
        document_url: str,
    ) -> None:
        """Handle HTTP status errors with retry logic.

        Args:
            error: The HTTP status error
            attempt: Current attempt number
            document_url: Document URL being processed

        Raises:
            APIClientError: If all retries exhausted
        """
        # Log the actual API response for debugging
        try:
            error_detail = error.response.json()
            LOGGER.error(
                f"Mistral OCR API error response: {error_detail}",
                extra={"document_url": document_url, "status_code": error.response.status_code}
            )
        except Exception:
            LOGGER.error(
                f"Mistral OCR API error response (text): {error.response.text}",
                extra={"document_url": document_url, "status_code": error.response.status_code}
            )
        
        if attempt < self.max_retries - 1:
            LOGGER.warning(
                f"Mistral OCR API call failed, retrying (attempt {attempt + 1}/{self.max_retries})",
                extra={
                    "document_url": document_url,
                    "status_code": error.response.status_code,
                    "error": str(error),
                },
            )
            await self._wait_before_retry(attempt)
        else:
            LOGGER.error(
                "Mistral OCR API call failed after all retries",
                exc_info=True,
                extra={
                    "document_url": document_url,
                    "status_code": error.response.status_code,
                },
            )
            raise APIClientError(
                f"Mistral OCR API returned error: {error.response.status_code}"
            ) from error

    async def _handle_timeout_error(
        self,
        error: httpx.TimeoutException,
        attempt: int,
        document_url: str,
    ) -> None:
        """Handle timeout errors with retry logic.

        Args:
            error: The timeout error
            attempt: Current attempt number
            document_url: Document URL being processed

        Raises:
            OCRTimeoutError: If all retries exhausted
        """
        if attempt < self.max_retries - 1:
            LOGGER.warning(
                f"Mistral OCR API call timed out, retrying (attempt {attempt + 1}/{self.max_retries})",
                extra={"document_url": document_url, "error": str(error)},
            )
            await self._wait_before_retry(attempt)
        else:
            LOGGER.error(
                "Mistral OCR API call timed out",
                exc_info=True,
                extra={"document_url": document_url},
            )
            raise OCRTimeoutError(
                f"OCR processing timed out after {self.timeout}s"
            ) from error

    async def _handle_generic_error(
        self,
        error: Exception,
        attempt: int,
        document_url: str,
    ) -> None:
        """Handle generic errors with retry logic.

        Args:
            error: The generic error
            attempt: Current attempt number
            document_url: Document URL being processed

        Raises:
            APIClientError: If all retries exhausted
        """
        if attempt < self.max_retries - 1:
            LOGGER.warning(
                f"Mistral OCR API call failed, retrying (attempt {attempt + 1}/{self.max_retries})",
                extra={"document_url": document_url, "error": str(error)},
            )
            await self._wait_before_retry(attempt)
        else:
            LOGGER.error(
                "Mistral OCR API call failed after all retries",
                exc_info=True,
                extra={"document_url": document_url},
            )
            raise APIClientError(f"Failed to call Mistral OCR API: {str(error)}") from error

    async def _wait_before_retry(self, attempt: int) -> None:
        """Wait before retrying with exponential backoff.

        Args:
            attempt: Current attempt number (0-indexed)
        """
        import asyncio

        wait_time = self.retry_delay * (2**attempt)
        LOGGER.debug("Waiting before retry", extra={"wait_seconds": wait_time})
        await asyncio.sleep(wait_time)
