"""Pydantic response models for OCR API endpoints."""

from typing import Dict, Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

class OCRExtractionResponse(BaseModel):
    """Response model for OCR extraction endpoint.

    Attributes:
        document_id: Unique identifier for the processed document
        text: Extracted text content from the document
        confidence: Confidence score of the extraction (0.0 to 1.0)
        status: Processing status
        metadata: Additional metadata about the extraction
        layout: Optional layout information with bounding boxes
    """

    document_id: UUID = Field(
        default_factory=uuid4,
        description="Unique identifier for the processed document",
    )
    text: str = Field(
        ...,
        description="Extracted text content from the document",
        min_length=1,
    )
    confidence: float = Field(
        ...,
        description="Confidence score of the extraction",
        ge=0.0,
        le=1.0,
    )
    status: str = Field(
        default="Completed",
        description="Processing status",
        examples=["Completed", "Failed", "Pending"],
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata about the extraction process",
    )
    layout: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional layout information with bounding boxes",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "document_id": "550e8400-e29b-41d4-a716-446655440000",
                    "text": "Policy Number: 12345ABC\nCoverage: Property Damage\nEffective Date: 2023-07-10",
                    "confidence": 0.97,
                    "status": "Completed",
                    "metadata": {
                        "service": "Mistral OCR",
                        "model": "pixtral-12b-2409",
                        "processing_time_seconds": 2.5,
                        "page_count": 3,
                    },
                }
            ]
        }
    }


class ErrorResponse(BaseModel):
    """Error response model.

    Attributes:
        error: Error type/category
        message: Human-readable error message
        detail: Optional detailed error information
    """

    error: str = Field(
        ...,
        description="Error type or category",
        examples=["OCRExtractionError", "ValidationError"],
    )
    message: str = Field(
        ...,
        description="Human-readable error message",
        examples=["Failed to extract text from document"],
    )
    detail: Optional[str] = Field(
        default=None,
        description="Detailed error information",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "error": "OCRExtractionError",
                    "message": "Failed to extract text from document",
                    "detail": "Document format not supported",
                }
            ]
        }
    }

