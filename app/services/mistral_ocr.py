"""Mistral OCR service implementation."""

import base64
import time
from typing import Dict, Any

import httpx

from app.services.ocr_base import BaseOCRService, OCRResult
from app.utils.exceptions import (
    OCRExtractionError,
    OCRTimeoutError,
    InvalidDocumentError,
    APIClientError,
)
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class MistralOCRService(BaseOCRService):
    """Mistral OCR service implementation using Pixtral model.

    This service uses Mistral's multimodal API to extract text from documents.
    It supports PDFs and images with high accuracy and structured output.

    Attributes:
        api_key: Mistral API key
        api_url: Mistral API endpoint URL
        model: Model name to use (default: pixtral-12b-2409)
        timeout: Request timeout in seconds
        max_retries: Maximum number of retry attempts
        retry_delay: Delay between retries in seconds
    """

    def __init__(
        self,
        api_key: str,
        api_url: str = "https://api.mistral.ai/v1/ocr",
        model: str = "mistral-ocr-latest",
        timeout: int = 120,
        max_retries: int = 3,
        retry_delay: int = 2,
    ):
        """Initialize Mistral OCR service.

        Args:
            api_key: Mistral API key
            api_url: Mistral API endpoint URL
            model: Model name to use
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
            retry_delay: Delay between retries
        """
        self.api_key = api_key
        self.api_url = api_url
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        LOGGER.info(
            "Initialized Mistral OCR service",
            extra={
                "model": self.model,
                "timeout": self.timeout,
                "max_retries": self.max_retries,
            },
        )

    async def extract_text_from_url(self, document_url: str) -> OCRResult:
        """Extract text from a document URL using Mistral OCR.

        Args:
            document_url: Public URL of the document to process

        Returns:
            OCRResult: Extracted text and metadata

        Raises:
            OCRExtractionError: If extraction fails
            OCRTimeoutError: If processing times out
            InvalidDocumentError: If document is invalid
        """
        LOGGER.info("Starting OCR extraction", extra={"document_url": document_url})
        start_time = time.time()

        try:
            # Download document
            document_data = await self._download_document(document_url)

            # Extract text using Mistral API
            extracted_text = await self._call_mistral_api(document_data, document_url)

            # Calculate processing time
            processing_time = time.time() - start_time

            # Create OCR result
            result = OCRResult(
                text=extracted_text,
                confidence=0.95,  # Mistral typically has high confidence
                metadata={
                    "service": self.get_service_name(),
                    "model": self.model,
                    "processing_time_seconds": round(processing_time, 2),
                    "document_url": document_url,
                },
            )

            LOGGER.info(
                "OCR extraction completed successfully",
                extra={
                    "document_url": document_url,
                    "text_length": len(extracted_text),
                    "processing_time": processing_time,
                },
            )

            return result

        except httpx.TimeoutException as e:
            LOGGER.error(
                "OCR extraction timed out",
                exc_info=True,
                extra={"document_url": document_url, "error": str(e)},
            )
            raise OCRTimeoutError(f"OCR processing timed out after {self.timeout}s") from e

        except (httpx.HTTPStatusError, httpx.RequestError) as e:
            LOGGER.error(
                "API request failed",
                exc_info=True,
                extra={"document_url": document_url, "error": str(e)},
            )
            raise APIClientError(f"Failed to communicate with Mistral API: {str(e)}") from e

        except Exception as e:
            LOGGER.error(
                "OCR extraction failed",
                exc_info=True,
                extra={"document_url": document_url, "error": str(e)},
            )
            raise OCRExtractionError(f"Failed to extract text from document: {str(e)}") from e

    async def _download_document(self, document_url: str) -> bytes:
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

    async def _call_mistral_api(self, document_data: bytes, document_url: str) -> str:
        """Call Mistral OCR API to extract text from document.

        Args:
            document_data: Document content as bytes (not used when using document_url)
            document_url: Original document URL

        Returns:
            str: Extracted text content

        Raises:
            APIClientError: If API call fails
        """
        # Prepare API request according to Mistral OCR API format
        # According to docs: https://docs.mistral.ai/capabilities/document_ai/basic_ocr
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # Use document_url directly (Mistral will download it)
        payload = {
            "model": self.model,
            "document": {
                "type": "document_url",
                "document_url": document_url,
            },
            "include_image_base64": False,  # We don't need images back
        }

        LOGGER.debug(
            "Calling Mistral OCR API",
            extra={"model": self.model, "document_url": document_url},
        )

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for attempt in range(self.max_retries):
                try:
                    response = await client.post(self.api_url, json=payload, headers=headers)
                    response.raise_for_status()

                    result = response.json()
                    
                    # Extract text from OCR API response format
                    # Response structure: {"pages": [{"markdown": "text content"}], ...}
                    pages = result.get("pages", [])
                    
                    # Combine text from all pages
                    extracted_text = ""
                    for page in pages:
                        page_text = page.get("markdown", page.get("text", ""))
                        if page_text:
                            extracted_text += page_text + "\n\n"
                    
                    extracted_text = extracted_text.strip()

                    LOGGER.debug(
                        "Mistral OCR API call successful",
                        extra={
                            "document_url": document_url,
                            "attempt": attempt + 1,
                            "pages_processed": len(pages),
                            "text_length": len(extracted_text),
                        },
                    )

                    return extracted_text

                except httpx.HTTPStatusError as e:
                    # Log the actual API response for debugging
                    try:
                        error_detail = e.response.json()
                        LOGGER.error(
                            f"Mistral OCR API error response: {error_detail}",
                            extra={"document_url": document_url, "status_code": e.response.status_code}
                        )
                    except Exception:
                        LOGGER.error(
                            f"Mistral OCR API error response (text): {e.response.text}",
                            extra={"document_url": document_url, "status_code": e.response.status_code}
                        )
                    
                    if attempt < self.max_retries - 1:
                        LOGGER.warning(
                            f"Mistral OCR API call failed, retrying (attempt {attempt + 1}/{self.max_retries})",
                            extra={
                                "document_url": document_url,
                                "status_code": e.response.status_code,
                                "error": str(e),
                            },
                        )
                        await self._wait_before_retry(attempt)
                    else:
                        LOGGER.error(
                            "Mistral OCR API call failed after all retries",
                            exc_info=True,
                            extra={
                                "document_url": document_url,
                                "status_code": e.response.status_code,
                            },
                        )
                        raise APIClientError(
                            f"Mistral OCR API returned error: {e.response.status_code}"
                        ) from e

                except Exception as e:
                    if attempt < self.max_retries - 1:
                        LOGGER.warning(
                            f"Mistral OCR API call failed, retrying (attempt {attempt + 1}/{self.max_retries})",
                            extra={"document_url": document_url, "error": str(e)},
                        )
                        await self._wait_before_retry(attempt)
                    else:
                        LOGGER.error(
                            "Mistral OCR API call failed after all retries",
                            exc_info=True,
                            extra={"document_url": document_url},
                        )
                        raise APIClientError(f"Failed to call Mistral OCR API: {str(e)}") from e

        raise APIClientError("Failed to extract text after all retry attempts")

    async def _wait_before_retry(self, attempt: int) -> None:
        """Wait before retrying with exponential backoff.

        Args:
            attempt: Current attempt number (0-indexed)
        """
        import asyncio

        wait_time = self.retry_delay * (2**attempt)
        LOGGER.debug("Waiting before retry", extra={"wait_seconds": wait_time})
        await asyncio.sleep(wait_time)

    def get_service_name(self) -> str:
        """Get the name of the OCR service.

        Returns:
            str: Service name
        """
        return "Mistral OCR"

