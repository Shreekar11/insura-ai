"""Pydantic response models for OCR API endpoints."""

from typing import Dict, Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field

class OCRExtractionResponse(BaseModel):
    """Response model for OCR extraction endpoint.

    Attributes:
        document_id: Unique identifier for the processed document
        status: Processing status
        metadata: Metadata about the extraction (pages, processing time, classification, etc.)
        text: Optional extracted text content (excluded by default to reduce response size)
        layout: Optional layout information with bounding boxes
    """

    document_id: Optional[UUID] = Field(
        default=None,
        description="Unique identifier for the processed document in database",
    )
    status: str = Field(
        default="Completed",
        description="Processing status",
        examples=["Completed", "Failed", "Pending"],
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadata about extraction: pages, processing time, classification, etc.",
    )
    text: Optional[str] = Field(
        default=None,
        description="Extracted text content (optional, excluded by default)",
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
                    "status": "Completed",
                    "metadata": {
                        "service": "Docling",
                        "processing_time_seconds": 2.5,
                        "pages_count": 3,
                        "raw_text_length": 5420,
                        "normalized_text_length": 4890,
                        "normalization_applied": True,
                        "classification": {
                            "classified_type": "policy",
                            "confidence": 0.89,
                            "method": "aggregate",
                            "fallback_used": False,
                            "chunks_used": 12
                        }
                    },
                }
            ]
        }
    }

class OCRNormalizeResponse(BaseModel):
    """Response model for text normalization.
    
    Attributes:
        original_text: Original raw text
        normalized_text: Cleaned and normalized text
        original_length: Length of original text
        normalized_length: Length of normalized text
        reduction_percent: Percentage reduction in text length
        success: Whether normalization was successful
    """
    
    original_text: str = Field(
        ...,
        description="Original raw OCR text",
    )
    normalized_text: str = Field(
        ...,
        description="Normalized and cleaned text",
    )
    original_length: int = Field(
        ...,
        description="Character count of original text",
        ge=0,
    )
    normalized_length: int = Field(
        ...,
        description="Character count of normalized text",
        ge=0,
    )
    reduction_percent: float = Field(
        ...,
        description="Percentage reduction in text length after normalization",
    )
    success: bool = Field(
        default=True,
        description="Whether normalization was successful",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "original_text": "Raw OCR text",
                    "normalized_text": "Cleaned and normalized text",
                    "original_length": 100,
                    "normalized_length": 80,
                    "reduction_percent": 20.0,
                    "success": True,
                }
            ]
        }
    }


class DocumentSectionsResponse(BaseModel):
    """Response model for document section detection.
    
    Attributes:
        sections: Dictionary mapping section names to line numbers
        section_count: Number of sections detected
        success: Whether detection was successful
    """
    
    sections: Dict[str, List[int]] = Field(
        default_factory=dict,
        description="Detected sections with line numbers where they appear",
        examples=[{
            "declarations": [1, 5],
            "coverages": [10],
            "endorsements": [20, 25]
        }],
    )
    section_count: int = Field(
        ...,
        description="Total number of sections detected",
        ge=0,
    )
    success: bool = Field(
        default=True,
        description="Whether section detection was successful",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "sections": {
                        "declarations": [1, 5],
                        "coverages": [10],
                        "endorsements": [20, 25]
                    },
                    "section_count": 3,
                    "success": True,
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

