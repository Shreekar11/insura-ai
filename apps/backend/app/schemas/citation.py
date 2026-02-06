"""Citation schemas for source mapping and PDF highlighting.

This module defines Pydantic models for citation data used to map
extracted items (coverages, exclusions, etc.) back to their source
locations in PDF documents.
"""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Dict, Any
from uuid import UUID
from enum import Enum

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    """Types of extracted items that can have citations."""

    EFFECTIVE_COVERAGE = "effective_coverage"
    EFFECTIVE_EXCLUSION = "effective_exclusion"
    ENDORSEMENT = "endorsement"
    CONDITION = "condition"
    CLAUSE = "clause"


class ExtractionMethod(str, Enum):
    """Methods used for coordinate extraction."""

    DOCLING = "docling"
    PDFPLUMBER = "pdfplumber"
    MANUAL = "manual"


class ResolutionMethod(str, Enum):
    """Methods used for citation coordinate resolution."""

    DIRECT_TEXT_MATCH = "direct_text_match"
    SEMANTIC_CHUNK_MATCH = "semantic_chunk_match"
    PLACEHOLDER = "placeholder"


class BoundingBox(BaseModel):
    """Bounding box in PDF coordinate system.

    PDF coordinates use bottom-left origin with Y increasing upward.
    Units are in PDF points (1 point = 1/72 inch).
    """

    x0: float = Field(..., description="Left coordinate (points)")
    y0: float = Field(..., description="Bottom coordinate (points)")
    x1: float = Field(..., description="Right coordinate (points)")
    y1: float = Field(..., description="Top coordinate (points)")

    @property
    def width(self) -> float:
        """Calculate width of bounding box."""
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        """Calculate height of bounding box."""
        return self.y1 - self.y0


class CitationSpan(BaseModel):
    """A single span of text in the PDF.

    Represents a contiguous region of text on a specific page.
    Multiple spans can be combined for multi-line or multi-region citations.
    """

    page_number: int = Field(..., ge=1, description="1-indexed page number")
    bounding_boxes: List[BoundingBox] = Field(
        ...,
        min_length=1,
        description="List of bounding boxes for this span (may be multiple for wrapped text)"
    )
    text_content: str = Field(..., description="Text content within this span")


class PageRange(BaseModel):
    """Page range for multi-page citations."""

    start: int = Field(..., ge=1, description="Start page (1-indexed)")
    end: int = Field(..., ge=1, description="End page (1-indexed)")


class PageDimensions(BaseModel):
    """Page dimensions for coordinate transformation."""

    page_number: int = Field(..., ge=1, description="1-indexed page number")
    width_points: float = Field(..., gt=0, description="Page width in PDF points")
    height_points: float = Field(..., gt=0, description="Page height in PDF points")
    rotation: int = Field(default=0, description="Page rotation in degrees (0, 90, 180, 270)")


# ============================================================================
# Request Schemas
# ============================================================================


class CitationCreate(BaseModel):
    """Schema for creating a new citation."""

    document_id: UUID = Field(..., description="Document UUID")
    source_type: SourceType = Field(..., description="Type of extracted item")
    source_id: str = Field(..., description="Canonical ID or stable ID of the source item")
    spans: List[CitationSpan] = Field(
        ...,
        min_length=1,
        description="Location spans in the PDF"
    )
    verbatim_text: str = Field(..., description="Exact extracted policy language")
    primary_page: int = Field(..., ge=1, description="Primary page for navigation")
    page_range: Optional[PageRange] = Field(
        None, description="Page range for multi-page citations"
    )
    extraction_confidence: Optional[Decimal] = Field(
        None, ge=0, le=1, description="Confidence score (0.0-1.0)"
    )
    extraction_method: ExtractionMethod = Field(
        default=ExtractionMethod.DOCLING,
        description="Method used for extraction"
    )
    clause_reference: Optional[str] = Field(
        None, description="Clause reference (e.g., 'SECTION II.B.3')"
    )
    resolution_method: Optional[str] = Field(
        None, description="How citation was resolved: direct_text_match, semantic_chunk_match, placeholder"
    )


class CitationBulkCreate(BaseModel):
    """Schema for bulk creating citations."""

    citations: List[CitationCreate] = Field(..., description="List of citations to create")


# ============================================================================
# Response Schemas
# ============================================================================


class CitationResponse(BaseModel):
    """API response for citation data."""

    id: UUID = Field(..., description="Citation UUID")
    document_id: UUID = Field(..., description="Document UUID")
    source_type: str = Field(..., description="Type of extracted item")
    source_id: str = Field(..., description="Canonical ID of the source item")
    spans: List[CitationSpan] = Field(..., description="Location spans in the PDF")
    verbatim_text: str = Field(..., description="Exact extracted policy language")
    primary_page: int = Field(..., description="Primary page for navigation")
    page_range: Optional[Dict[str, int]] = Field(
        None, description="Page range: {start: int, end: int}"
    )
    extraction_confidence: Optional[float] = Field(
        None, description="Confidence score (0.0-1.0)"
    )
    extraction_method: str = Field(..., description="Method used for extraction")
    clause_reference: Optional[str] = Field(
        None, description="Clause reference"
    )
    resolution_method: Optional[str] = Field(
        None, description="How citation was resolved: direct_text_match, semantic_chunk_match, placeholder"
    )
    created_at: datetime = Field(..., description="Creation timestamp")

    class Config:
        from_attributes = True


class CitationListResponse(BaseModel):
    """Response for listing citations."""

    document_id: UUID = Field(..., description="Document UUID")
    citations: List[CitationResponse] = Field(..., description="List of citations")
    total: int = Field(..., description="Total number of citations")


class PageDimensionsResponse(BaseModel):
    """Response for page dimensions."""

    document_id: UUID = Field(..., description="Document UUID")
    page_number: int = Field(..., description="Page number")
    width_points: float = Field(..., description="Page width in PDF points")
    height_points: float = Field(..., description="Page height in PDF points")
    rotation: int = Field(default=0, description="Page rotation in degrees")


class DocumentPagesResponse(BaseModel):
    """Response for all page dimensions in a document."""

    document_id: UUID = Field(..., description="Document UUID")
    pages: List[PageDimensions] = Field(..., description="List of page dimensions")
    total_pages: int = Field(..., description="Total number of pages")


# ============================================================================
# Internal Schemas (for service layer)
# ============================================================================


class WordCoordinate(BaseModel):
    """Word with its bounding box coordinates.

    Used internally by the coordinate extraction service.
    """

    text: str = Field(..., description="Word text")
    page_number: int = Field(..., ge=1, description="1-indexed page number")
    x0: float = Field(..., description="Left coordinate")
    y0: float = Field(..., description="Bottom coordinate (PDF coords)")
    x1: float = Field(..., description="Right coordinate")
    y1: float = Field(..., description="Top coordinate (PDF coords)")


class TextMatch(BaseModel):
    """Result of text matching operation.

    Returned by the CitationMapper when finding text locations.
    """

    matched_text: str = Field(..., description="The text that was matched")
    spans: List[CitationSpan] = Field(..., description="Location spans")
    confidence: float = Field(..., ge=0, le=1, description="Match confidence")
    page_number: int = Field(..., description="Primary page number")


__all__ = [
    # Enums
    "SourceType",
    "ExtractionMethod",
    "ResolutionMethod",
    # Core models
    "BoundingBox",
    "CitationSpan",
    "PageRange",
    "PageDimensions",
    # Request schemas
    "CitationCreate",
    "CitationBulkCreate",
    # Response schemas
    "CitationResponse",
    "CitationListResponse",
    "PageDimensionsResponse",
    "DocumentPagesResponse",
    # Internal schemas
    "WordCoordinate",
    "TextMatch",
]
