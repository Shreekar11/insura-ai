"""Base OCR service interface for pluggable OCR implementations."""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class OCRResult:
    """OCR extraction result container.

    Attributes:
        text: Extracted text content
        confidence: Confidence score (0.0 to 1.0)
        metadata: Additional metadata (page_count, processing_time, etc.)
        layout: Optional layout information with bounding boxes
    """

    def __init__(
        self,
        text: str,
        confidence: float,
        metadata: Optional[Dict[str, Any]] = None,
        layout: Optional[Dict[str, Any]] = None,
    ):
        """Initialize OCR result.

        Args:
            text: Extracted text content
            confidence: Confidence score between 0.0 and 1.0
            metadata: Optional metadata dictionary
            layout: Optional layout information
        """
        self.text = text
        self.confidence = confidence
        self.metadata = metadata or {}
        self.layout = layout

    def to_dict(self) -> Dict[str, Any]:
        """Convert OCR result to dictionary.

        Returns:
            Dict[str, Any]: Dictionary representation of OCR result
        """
        result = {
            "text": self.text,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }
        if self.layout:
            result["layout"] = self.layout
        return result


class BaseOCRService(ABC):
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

