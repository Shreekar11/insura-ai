"""OCR service for document text extraction and processing."""

import time
from typing import Dict, Any, List

from app.repositories.ocr_repository import OCRRepository
from app.services.ocr.ocr_base import BaseOCRService, OCRResult
from app.services.normalization.normalization_service import NormalizationService
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

    This service orchestrates the OCR extraction process using the Mistral API
    and includes comprehensive text normalization for insurance documents.
    It handles business logic, validation, and coordinates between the repository
    layer and the API endpoints.

    Attributes:
        repository: OCR repository for external interactions
        normalization_service: Service for normalizing OCR text
        model: Model name to use for OCR
    """

    def __init__(
        self,
        api_key: str,
        openrouter_api_key: str,
        api_url: str = "https://api.mistral.ai/v1/ocr",
        model: str = "mistral-ocr-latest",
        openrouter_api_url: str = "https://openrouter.ai/api/v1/ocr",
        openrouter_model: str = "mistral-medium-2508",
        timeout: int = 120,
        max_retries: int = 3,
        retry_delay: int = 2,
        use_hybrid_normalization: bool = True,
    ):
        """Initialize OCR service.

        Args:
            api_key: Mistral API key
            openrouter_api_key: OpenRouter API key for LLM normalization
            api_url: Mistral API endpoint URL
            model: Model name to use
            openrouter_api_url: OpenRouter API endpoint URL
            openrouter_model: OpenRouter model name for normalization
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
            retry_delay: Delay between retries in seconds
            use_hybrid_normalization: Use hybrid LLM + code normalization (default: True)
        """
        self.model = model
        self.repository = OCRRepository(
            api_key=api_key,
            api_url=api_url,
            timeout=timeout,
            max_retries=max_retries,
            retry_delay=retry_delay,
        )
        self.normalization_service = NormalizationService(
            openrouter_api_key=openrouter_api_key,
            openrouter_api_url=openrouter_api_url,
            openrouter_model=openrouter_model,
            use_hybrid=use_hybrid_normalization,
        )

        LOGGER.info(
            "Initialized OCR service",
            extra={
                "model": self.model,
                "service_name": self.get_service_name(),
                "use_hybrid_normalization": use_hybrid_normalization,
            },
        )

    async def extract_text_from_url(
        self,
        document_url: str,
        normalize: bool = True
    ) -> OCRResult:
        """Extract text from a document URL using OCR.

        This method orchestrates the complete OCR extraction process:
        1. Validates the document URL
        2. Downloads the document (via repository)
        3. Calls Mistral OCR API (via repository)
        4. Normalizes the extracted text (optional)
        5. Processes and returns the result

        Args:
            document_url: Public URL of the document to process
            normalize: Whether to apply text normalization (default: True)

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

            # Extract text using Mistral API - returns List[PageData]
            pages = await self.repository.call_mistral_ocr_api(
                document_url=document_url,
                model=self.model,
            )

            # Validate extraction result
            self._validate_extraction_result(pages, document_url)

            # Normalize text if requested
            normalized_text = ""
            normalization_applied = False
            
            if normalize:
                LOGGER.info("Applying page-specific text normalization")
                normalized_text = await self.normalization_service.normalize_pages(
                    pages=pages
                )
                normalization_applied = True
                
                LOGGER.info(
                    "Page-specific normalization completed",
                    extra={
                        "pages_count": len(pages),
                        "normalized_length": len(normalized_text),
                    }
                )
            else:
                # Combine pages without normalization
                page_parts = []
                for page in pages:
                    page_text = page.get_content(prefer_markdown=True)
                    if page_text.strip():
                        page_parts.append(f"=== PAGE {page.page_number} ===\n{page_text}")
                normalized_text = "\n\n".join(page_parts)

            # Calculate processing time
            processing_time = time.time() - start_time

            # Create OCR result
            result = self._create_ocr_result(
                pages=pages,
                normalized_text=normalized_text,
                document_url=document_url,
                processing_time=processing_time,
                normalization_applied=normalization_applied,
            )

            LOGGER.info(
                "OCR extraction completed successfully",
                extra={
                    "document_url": document_url,
                    "pages_count": len(pages),
                    "normalized_text_length": len(normalized_text),
                    "processing_time": processing_time,
                    "normalization_applied": normalization_applied,
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

    def _validate_extraction_result(self, pages: List, document_url: str) -> None:
        """Validate OCR extraction result.

        Args:
            pages: List of PageData objects from extraction
            document_url: Document URL being processed

        Raises:
            OCRExtractionError: If extraction result is invalid
        """
        if not pages:
            LOGGER.warning(
                "OCR extraction returned no pages",
                extra={"document_url": document_url},
            )
            raise OCRExtractionError("OCR extraction returned no pages")

        total_text_length = sum(len(page) for page in pages)
        if total_text_length < 10:
            LOGGER.warning(
                "OCR extraction returned suspiciously short text",
                extra={
                    "document_url": document_url,
                    "pages_count": len(pages),
                    "total_text_length": total_text_length,
                },
            )

        LOGGER.debug(
            "Extraction result validated",
            extra={
                "document_url": document_url,
                "pages_count": len(pages),
                "total_text_length": total_text_length,
            },
        )

    def _create_ocr_result(
        self,
        pages: List,
        normalized_text: str,
        document_url: str,
        processing_time: float,
        normalization_applied: bool,
    ) -> OCRResult:
        """Create OCR result object with metadata.

        Args:
            pages: List of PageData objects from extraction
            normalized_text: Normalized text content
            document_url: Source document URL
            processing_time: Time taken for processing in seconds
            normalization_applied: Whether normalization was applied

        Returns:
            OCRResult: Complete OCR result with metadata
        """
        # Calculate raw text length from all pages
        raw_text_length = sum(len(page) for page in pages)
        
        # Use normalized text if applied, otherwise combine pages
        if normalization_applied:
            final_text = normalized_text
        else:
            page_parts = []
            for page in pages:
                page_text = page.get_content(prefer_markdown=True)
                if page_text.strip():
                    page_parts.append(f"=== PAGE {page.page_number} ===\n{page_text}")
            final_text = "\n\n".join(page_parts)
        
        return OCRResult(
            text=final_text,
            confidence=0.95,  # Mistral typically has high confidence
            metadata={
                "service": self.get_service_name(),
                "model": self.model,
                "processing_time_seconds": round(processing_time, 2),
                "document_url": document_url,
                "pages_count": len(pages),
                "raw_text_length": raw_text_length,
                "normalized_text_length": len(normalized_text) if normalization_applied else len(final_text),
                "text_length": len(final_text),
                "word_count": len(final_text.split()),
                "normalization_applied": normalization_applied,
                "text_reduction_percent": round(
                    (1 - len(normalized_text) / raw_text_length) * 100, 2
                ) if normalization_applied and raw_text_length > 0 else 0.0,
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

        This method provides direct access to the normalization service
        for cases where text has already been extracted and needs to be
        normalized separately.

        Args:
            text: Raw OCR text to normalize

        Returns:
            str: Normalized text
            
        Example:
            >>> service = OCRService(api_key="...")
            >>> raw_text = "PoIicy Number: 12345\\nPage 1 of 5"
            >>> normalized = await service.normalize_text(raw_text)
            >>> print(normalized)
            Policy Number: 12345
        """
        return self.normalization_service.normalize_text(text)
    
    async def normalize_page_text(
        self,
        page_text: str,
        page_number: int
    ) -> Dict[str, Any]:
        """Normalize text from a single page.

        This method is useful for page-level processing and debugging.
        It provides detailed metadata about the normalization process.

        Args:
            page_text: Raw text from a single page
            page_number: Page number for logging

        Returns:
            dict: Dictionary containing normalized text and metadata
            
        Example:
            >>> service = OCRService(api_key="...")
            >>> result = await service.normalize_page_text(page_text, 1)
            >>> print(result["normalized_text"])
        """
        return self.normalization_service.normalize_page_text(
            page_text=page_text,
            page_number=page_number,
        )
    
    async def detect_document_sections(self, text: str) -> Dict[str, list]:
        """Detect common insurance document sections.

        This method identifies key sections in insurance documents which
        can be useful for downstream classification and extraction.

        Args:
            text: Normalized document text

        Returns:
            dict: Dictionary mapping section names to line numbers where found
            
        Example:
            >>> service = OCRService(api_key="...")
            >>> sections = await service.detect_document_sections(text)
            >>> print(sections)
            {'declarations': [1, 5], 'coverages': [10, 15]}
        """
        return self.normalization_service.detect_document_sections(text)
