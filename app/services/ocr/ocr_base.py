"""Base OCR service interface for pluggable OCR implementations."""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from uuid import UUID

from app.core.base_service import BaseService


class OCRResult:
    """OCR extraction result container.

    Attributes:
        text: Extracted text content
        confidence: Confidence score (0.0 to 1.0)
        metadata: Additional metadata (page_count, processing_time, etc.)
        layout: Optional layout information with bounding boxes
        document_id: Optional document ID from database
        success: Whether extraction was successful
        error: Optional error message
    """

    def __init__(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
        layout: Optional[Dict[str, Any]] = None,
        document_id: Optional[UUID] = None,
        success: bool = True,
        error: Optional[str] = None,
    ):
        """Initialize OCR result.

        Args:
            text: Extracted text content
            metadata: Optional metadata dictionary
            layout: Optional layout information
            document_id: Optional document ID from database
            success: Whether extraction was successful
            error: Optional error message
        """
        self.text = text
        self.metadata = metadata or {}
        self.layout = layout
        self.document_id = document_id
        self.success = success
        self.error = error
        
        # Extract confidence from metadata if available
        self.confidence = self.metadata.get("confidence", 0.95)

    def to_dict(self) -> Dict[str, Any]:
        """Convert OCR result to dictionary.

        Returns:
            Dict[str, Any]: Dictionary representation of OCR result
        """
        result = {
            "text": self.text,
            "confidence": self.confidence,
            "metadata": self.metadata,
            "success": self.success,
        }
        if self.layout:
            result["layout"] = self.layout
        if self.document_id:
            result["document_id"] = str(self.document_id)
        if self.error:
            result["error"] = self.error
        return result


class BaseOCRService(BaseService):
    """Abstract base class for OCR service implementations.

    This class defines the interface that all OCR service implementations
    must follow, enabling pluggable OCR providers (Mistral, Tesseract, etc.).
    """

    @abstractmethod
    async def extract_text_from_url(self, document_url: str) -> OCRResult:
        """Extract text from a document URL.

        Args:
            document_url: Public URL of the document to process

        Returns:
            OCRResult: Extracted text and metadata

        Raises:
            OCRExtractionError: If extraction fails
            OCRTimeoutError: If processing times out
            InvalidDocumentError: If document is invalid
        """
        pass

    @abstractmethod
    def get_service_name(self) -> str:
        """Get the name of the OCR service.

        Returns:
            str: Service name (e.g., "Mistral OCR", "Tesseract")
        """
        pass

