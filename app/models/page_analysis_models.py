"""Data models for page-level analysis and classification.

This module defines the data structures used throughout the page analysis pipeline,
including page signals, classifications, and manifests.
"""

from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional, List
from uuid import UUID


class PageType(str, Enum):
    """Types of pages found in insurance documents."""
    
    DECLARATIONS = "declarations"
    COVERAGES = "coverages"
    CONDITIONS = "conditions"
    EXCLUSIONS = "exclusions"
    ENDORSEMENT = "endorsement"
    SOV = "sov"  # Schedule of Values
    LOSS_RUN = "loss_run"
    INVOICE = "invoice"
    BOILERPLATE = "boilerplate"
    DUPLICATE = "duplicate"
    UNKNOWN = "unknown"


class PageSignals(BaseModel):
    """Signals extracted from a single page.
    
    These signals are extracted without full OCR to enable fast page classification.
    """
    
    page_number: int = Field(..., description="1-indexed page number")
    top_lines: List[str] = Field(
        ..., 
        description="First 5-10 lines of text from the page"
    )
    text_density: float = Field(
        ..., 
        ge=0.0, 
        le=1.0,
        description="Ratio of text to page area (0.0 = empty, 1.0 = full)"
    )
    has_tables: bool = Field(
        ..., 
        description="Whether the page contains table structures"
    )
    max_font_size: Optional[float] = Field(
        None, 
        description="Largest font size on page (indicates headers)"
    )
    page_hash: str = Field(
        ..., 
        description="Hash of page content for duplicate detection"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "page_number": 12,
                "top_lines": [
                    "DECLARATIONS PAGE",
                    "Policy Number: ABC-123456",
                    "Named Insured: XYZ Manufacturing LLC"
                ],
                "text_density": 0.82,
                "has_tables": False,
                "max_font_size": 22.0,
                "page_hash": "a3f5e9..."
            }
        }


class PageClassification(BaseModel):
    """Classification result for a single page."""
    
    page_number: int = Field(..., description="1-indexed page number")
    page_type: PageType = Field(..., description="Classified page type")
    confidence: float = Field(
        ..., 
        ge=0.0, 
        le=1.0,
        description="Classification confidence score"
    )
    should_process: bool = Field(
        ..., 
        description="Whether this page should undergo full OCR and extraction"
    )
    duplicate_of: Optional[int] = Field(
        None, 
        description="Page number this is a duplicate of (if applicable)"
    )
    reasoning: Optional[str] = Field(
        None, 
        description="Human-readable explanation of classification"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "page_number": 12,
                "page_type": "declarations",
                "confidence": 0.98,
                "should_process": True,
                "duplicate_of": None,
                "reasoning": "Contains 'DECLARATIONS PAGE' and 'Policy Number' keywords"
            }
        }


class PageManifest(BaseModel):
    """Complete page analysis manifest for a document.
    
    This manifest determines which pages will be processed and which will be skipped.
    """
    
    document_id: UUID = Field(..., description="Document UUID")
    total_pages: int = Field(..., gt=0, description="Total number of pages in document")
    pages_to_process: List[int] = Field(
        ..., 
        description="List of page numbers that should be processed"
    )
    pages_skipped: List[int] = Field(
        ..., 
        description="List of page numbers that will be skipped"
    )
    classifications: List[PageClassification] = Field(
        ..., 
        description="Classification results for all pages"
    )
    
    @property
    def processing_ratio(self) -> float:
        """Percentage of pages that will be processed (0.0 to 1.0)."""
        if self.total_pages == 0:
            return 0.0
        return len(self.pages_to_process) / self.total_pages
    
    @property
    def cost_savings_estimate(self) -> float:
        """Estimated cost savings percentage (0.0 to 1.0)."""
        return 1.0 - self.processing_ratio
    
    def get_pages_by_type(self, page_type: PageType) -> List[int]:
        """Get all page numbers of a specific type."""
        return [
            c.page_number 
            for c in self.classifications 
            if c.page_type == page_type
        ]
    
    class Config:
        json_schema_extra = {
            "example": {
                "document_id": "550e8400-e29b-41d4-a716-446655440000",
                "total_pages": 120,
                "pages_to_process": [1, 2, 3, 10, 15, 80],
                "pages_skipped": [4, 5, 6, 7, 8, 9, 11, 12],
                "classifications": [],
                "processing_ratio": 0.15,
                "cost_savings_estimate": 0.85
            }
        }
