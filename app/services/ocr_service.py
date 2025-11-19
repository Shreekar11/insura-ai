"""OCR service for document text extraction and processing."""

import time
from typing import Dict, Any

from app.repositories.ocr_repository import OCRRepository
from app.services.ocr_base import BaseOCRService, OCRResult
from app.utils.exceptions import (
    OCRExtractionError,
    OCRTimeoutError,
    InvalidDocumentError,
    APIClientError,
)
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class OCRService(BaseOCRService):
    """OCR service implementation for extracting text from documents.

    This service orchestrates the OCR extraction process using the Mistral API.
    It handles business logic, validation, and coordinates between the repository
    layer and the API endpoints.

    Attributes:
        repository: OCR repository for external interactions
        model: Model name to use for OCR
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
        """Initialize OCR service.

        Args:
            api_key: Mistral API key
            api_url: Mistral API endpoint URL
            model: Model name to use
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
            retry_delay: Delay between retries in seconds
        """
        self.model = model
        self.repository = OCRRepository(
            api_key=api_key,
            api_url=api_url,
            timeout=timeout,
            max_retries=max_retries,
            retry_delay=retry_delay,
        )

        LOGGER.info(
            "Initialized OCR service",
            extra={
                "model": self.model,
                "service_name": self.get_service_name(),
            },
        )

    async def extract_text_from_url(self, document_url: str) -> OCRResult:
        """Extract text from a document URL using OCR.

        This method orchestrates the complete OCR extraction process:
        1. Validates the document URL
        2. Downloads the document (via repository)
        3. Calls Mistral OCR API (via repository)
        4. Processes and returns the result

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
            # Validate document URL
            self._validate_document_url(document_url)

            # Download document (validation check)
            await self.repository.download_document(document_url)

            # Extract text using Mistral API
            extracted_text = await self.repository.call_mistral_ocr_api(
                document_url=document_url,
                model=self.model,
            )

            # Validate extraction result
            self._validate_extraction_result(extracted_text, document_url)

            # Calculate processing time
            processing_time = time.time() - start_time

            # Create OCR result
            result = self._create_ocr_result(
                extracted_text=extracted_text,
                document_url=document_url,
                processing_time=processing_time,
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

        except (InvalidDocumentError, APIClientError, OCRTimeoutError):
            # Re-raise known exceptions
            raise

        except Exception as e:
            LOGGER.error(
                "OCR extraction failed",
                exc_info=True,
                extra={"document_url": document_url, "error": str(e)},
            )
            raise OCRExtractionError(f"Failed to extract text from document: {str(e)}") from e

    def _validate_document_url(self, document_url: str) -> None:
        """Validate document URL format.

        Args:
            document_url: URL to validate

        Raises:
            InvalidDocumentError: If URL is invalid
        """
        if not document_url:
            raise InvalidDocumentError("Document URL cannot be empty")

        if not document_url.startswith(("http://", "https://")):
            raise InvalidDocumentError("Document URL must start with http:// or https://")

        LOGGER.debug("Document URL validated", extra={"document_url": document_url})

    def _validate_extraction_result(self, extracted_text: str, document_url: str) -> None:
        """Validate OCR extraction result.

        Args:
            extracted_text: Extracted text to validate
            document_url: Document URL being processed

        Raises:
            OCRExtractionError: If extraction result is invalid
        """
        if not extracted_text:
            LOGGER.warning(
                "OCR extraction returned empty text",
                extra={"document_url": document_url},
            )
            raise OCRExtractionError("OCR extraction returned empty text")

        if len(extracted_text.strip()) < 10:
            LOGGER.warning(
                "OCR extraction returned suspiciously short text",
                extra={
                    "document_url": document_url,
                    "text_length": len(extracted_text),
                },
            )

        LOGGER.debug(
            "Extraction result validated",
            extra={
                "document_url": document_url,
                "text_length": len(extracted_text),
            },
        )

    def _create_ocr_result(
        self,
        extracted_text: str,
        document_url: str,
        processing_time: float,
    ) -> OCRResult:
        """Create OCR result object with metadata.

        Args:
            extracted_text: Extracted text content
            document_url: Source document URL
            processing_time: Time taken for processing in seconds

        Returns:
            OCRResult: Complete OCR result with metadata
        """
        return OCRResult(
            text=extracted_text,
            confidence=0.95,  # Mistral typically has high confidence
            metadata={
                "service": self.get_service_name(),
                "model": self.model,
                "processing_time_seconds": round(processing_time, 2),
                "document_url": document_url,
                "text_length": len(extracted_text),
                "word_count": len(extracted_text.split()),
            },
        )

    def get_service_name(self) -> str:
        """Get the name of the OCR service.

        Returns:
            str: Service name
        """
        return "Mistral OCR"

    async def normalize_text(self, text: str) -> str:
        """Normalize OCR text for better processing.

        This is a placeholder for future OCR normalization logic
        as described in the context document.

        Args:
            text: Raw OCR text to normalize

        Returns:
            str: Normalized text
        """
        # TODO: Implement OCR normalization as per context.md:
        # - Remove extra whitespace
        # - Normalize hyphenation
        # - Remove headers/footers
        # - Collapse broken words
        # - Remove non-ASCII OCR artifacts
        # - Fix common OCR errors (PoIicy → Policy, C1aim → Claim)
        # - Insurance-specific cleaning
        
        LOGGER.debug("Text normalization not yet implemented")
        return text
