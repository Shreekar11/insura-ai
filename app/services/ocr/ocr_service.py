"""OCR service for document text extraction and processing."""

import time
from typing import Dict, Any, List, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.ocr_repository import OCRRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.chunk_repository import ChunkRepository
from app.services.ocr.ocr_base import BaseOCRService, OCRResult
from app.services.normalization.normalization_service import NormalizationService
from app.services.classification.classification_service import ClassificationService
from app.services.classification.fallback_classifier import FallbackClassifier
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
        gemini_api_key: str,
        db_session: Optional[AsyncSession] = None,
        api_url: str = "https://api.mistral.ai/v1/ocr",
        model: str = "mistral-ocr-latest",
        gemini_model: str = "gemini-2.0-flash",
        timeout: int = 120,
        max_retries: int = 3,
        retry_delay: int = 2,
        use_hybrid_normalization: bool = True,
        enable_classification: bool = True,
        normalization_service: Optional[NormalizationService] = None,
        provider: str = "gemini",
        openrouter_api_key: Optional[str] = None,
        openrouter_model: str = "google/gemini-2.0-flash-001",
        openrouter_api_url: str = "https://openrouter.ai/api/v1/chat/completions",
    ):
        """Initialize OCR service.

        Args:
            api_key: Mistral API key
            gemini_api_key: Gemini API key for LLM normalization
            db_session: Database session for classification persistence
            api_url: Mistral API endpoint URL
            model: Model name to use
            gemini_model: Gemini model name for normalization
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
            retry_delay: Delay between retries in seconds
            use_hybrid_normalization: Use hybrid LLM + code normalization (default: True)
            enable_classification: Enable document classification (default: True)
            normalization_service: Optional injected NormalizationService
            provider: LLM provider to use ("gemini" or "openrouter")
            openrouter_api_key: OpenRouter API key
            openrouter_model: OpenRouter model name
            openrouter_api_url: OpenRouter API URL
        """
        super().__init__(repository=None)
        
        self.model = model
        self.enable_classification = enable_classification
        self.provider = provider
        self.gemini_api_key = gemini_api_key
        self.gemini_model = gemini_model
        self.openrouter_api_key = openrouter_api_key
        self.openrouter_model = openrouter_model
        self.openrouter_api_url = openrouter_api_url
        
        self.ocr_client = OCRRepository(
            api_key=api_key,
            api_url=api_url,
            timeout=timeout,
            max_retries=max_retries,
            retry_delay=retry_delay,
        )
        
        # Initialize classification services if enabled
        classification_service = None
        fallback_classifier = None
        chunk_repository = None
        self.document_repository = None
        
        if db_session:
            self.document_repository = DocumentRepository(db_session)
            # Set the primary repository for BaseService
            self.repository = self.document_repository
            
            if enable_classification:
                classification_service = ClassificationService()
                fallback_classifier = FallbackClassifier(
                    provider=provider,
                    gemini_api_key=gemini_api_key,
                    gemini_model=gemini_model,
                    openrouter_api_key=openrouter_api_key,
                    openrouter_model=openrouter_model,
                    openrouter_api_url=openrouter_api_url,
                )
                chunk_repository = ChunkRepository(db_session)
        
        # Use injected service or create new one
        if normalization_service:
            self.normalization_service = normalization_service
        else:
            self.normalization_service = NormalizationService(
                provider=provider,
                gemini_api_key=gemini_api_key,
                gemini_model=gemini_model,
                openrouter_api_key=openrouter_api_key,
                openrouter_model=openrouter_model,
                openrouter_api_url=openrouter_api_url,
                use_hybrid=use_hybrid_normalization,
                classification_service=classification_service,
                fallback_classifier=fallback_classifier,
                chunk_repository=chunk_repository,
                normalization_repository=NormalizationRepository(db_session) if db_session else None,
                classification_repository=ClassificationRepository(db_session) if db_session else None,
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
        document_id: Optional[UUID] = None,
    ) -> OCRResult:
        """Wrapper for run() to maintain backward compatibility.
        
        Delegates to BaseService.execute().
        """
        return await self.execute(
            document_url=document_url,
            document_id=document_id
        )

    async def run(
        self,
        document_url: str,
        document_id: Optional[UUID] = None,
    ) -> OCRResult:
        """Extract text from a document URL using Mistral OCR API.
        
        This method always uses hybrid normalization with chunking and classification.

        Args:
            document_url: Public URL to the document (PDF or image)
            document_id: Optional document ID for database tracking

        Returns:
            OCRResult: Extraction result with normalized text and classification

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

            # Download document (validation check whether the document is a PDF or an image)
            await self.ocr_client.download_document(document_url)

            # Extract text using Mistral API - returns List[PageData]
            pages = await self.ocr_client.call_mistral_ocr_api(
                document_url=document_url,
                model=self.model,
            )
            
            # Create document record if not provided and repository is available
            if document_id is None and self.document_repository:
                # Default test user UUID (same as before)
                DEFAULT_TEST_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
                
                document = await self.document_repository.create_document(
                    file_path=document_url,
                    page_count=len(pages),
                    user_id=DEFAULT_TEST_USER_ID,
                )
                document_id = document.id
                LOGGER.info(
                    "Document record created via repository",
                    extra={"document_id": str(document_id)}
                )

            # Validate extraction result
            self._validate_extraction_result(pages, document_url)

            # Always normalize with classification and chunking (hybrid method)
            LOGGER.info("Applying hybrid normalization with classification and chunking")
            normalized_text, classification_result = await self.normalization_service.normalize_and_classify_pages(
                pages=pages,
                document_id=document_id,
            )
            
            LOGGER.info(
                "Normalization and classification completed",
                extra={
                    "pages_count": len(pages),
                    "normalized_length": len(normalized_text),
                    "classified_type": classification_result.get("classified_type") if classification_result else None,
                    "confidence": classification_result.get("confidence") if classification_result else None,
                }
            )

            # Calculate processing time
            processing_time = time.time() - start_time

            # Create OCR result
            result = self._create_ocr_result(
                pages=pages,
                normalized_text=normalized_text,
                document_url=document_url,
                processing_time=processing_time,
                normalization_applied=True,
                classification_result=classification_result,
                document_id=document_id,
            )

            LOGGER.info(
                "OCR extraction completed successfully",
                extra={
                    "document_url": document_url,
                    "pages_count": len(pages),
                    "normalized_text_length": len(normalized_text),
                    "processing_time": processing_time,
                    "normalization_applied": True,
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
        classification_result: Optional[Dict[str, Any]] = None,
        document_id: Optional[UUID] = None,
    ) -> OCRResult:
        """Create OCR result object from extraction data.

        Args:
            pages: List of PageData objects
            normalized_text: Normalized text
            document_url: Document URL
            processing_time: Processing time in seconds
            normalization_applied: Whether normalization was applied
            classification_result: Classification result (optional)
            document_id: Document ID from database (optional)

        Returns:
            OCRResult: Complete OCR result
        """
        # Calculate total text length from pages
        raw_text_length = sum(len(page.get_content()) for page in pages)
        
        # Build metadata
        metadata = {
            "service": self.get_service_name(),
            "model": self.model,
            "processing_time_seconds": round(processing_time, 2),
            "document_url": document_url,
            "pages_count": len(pages),
            "raw_text_length": raw_text_length,
            "normalized_text_length": len(normalized_text),
            "normalization_applied": normalization_applied,
        }
        
        # Add classification metadata if available
        if classification_result:
            metadata["classification"] = {
                "classified_type": classification_result.get("classified_type"),
                "confidence": classification_result.get("confidence"),
                "method": classification_result.get("method"),
                "fallback_used": classification_result.get("fallback_used", False),
                "chunks_used": classification_result.get("chunks_used", 0),
            }

        return OCRResult(
            text=normalized_text,
            metadata=metadata,
            document_id=document_id,
            success=True,
            error=None,
        )

    def get_service_name(self) -> str:
        """Get the name of the OCR service.

        Returns:
            str: Service name
        """
        return "Mistral OCR"
