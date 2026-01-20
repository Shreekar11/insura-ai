"""Data models for page-level analysis and classification.

This module defines the data structures used throughout the page analysis pipeline,
including page signals, classifications, manifests, and document profiles.
"""

from enum import Enum
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List, Dict, Any
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
    DEFINITIONS = "definitions"
    TABLE_OF_CONTENTS = "table_of_contents"
    VEHICLE_DETAILS = "vehicle_details"
    INSURED_DECLARED_VALUE = "insured_declared_value"
    LIABILITY_COVERAGES = "liability_coverages"
    DEDUCTIBLES = "deductibles"
    PREMIUM = "premium"
    COVERAGES_CONTEXT = "coverages_context"
    ACORD_APPLICATION = "acord_application"
    PROPOSAL = "proposal"
    CERTIFICATE_OF_INSURANCE = "certificate_of_insurance"
    UNKNOWN = "unknown"


class SemanticSection(str, Enum):
    """Semantic insurance document section types.
    
    These represent high-level insurance concepts, distinct from visual page types.
    """
    CERTIFICATE_OF_INSURANCE = "certificate_of_insurance"
    DECLARATIONS = "declarations"
    COVERAGES = "coverages"
    LIABILITY_COVERAGE = "liability.coverage"
    LIABILITY_EXCLUSIONS = "liability.exclusions"
    PHYSICAL_DAMAGE_COVERAGE = "physical_damage.coverage"
    PHYSICAL_DAMAGE_EXCLUSIONS = "physical_damage.exclusions"
    MULTI_COVERAGE = "multi_coverage"
    CONDITIONS = "conditions"
    DEFINITIONS = "definitions"
    ENDORSEMENT = "endorsement"
    EXCLUSIONS = "exclusions"
    CERTIFICATE = "certificate"
    BOILERPLATE = "boilerplate"
    SOV = "sov"
    LOSS_RUN = "loss_run"
    TABLE_OF_CONTENTS = "toc"
    UNKNOWN = "unknown"


class DocumentType(str, Enum):
    """Types of insurance documents."""
    
    POLICY = "policy"
    POLICY_BUNDLE = "policy_bundle"
    SOV = "sov"
    LOSS_RUN = "loss_run"
    ENDORSEMENT = "endorsement"
    QUOTE = "quote"
    SUBMISSION = "submission"
    ACORD_APPLICATION = "acord_application"
    PROPOSAL = "proposal"
    INVOICE = "invoice"
    CERTIFICATE = "certificate"
    CORRESPONDENCE = "correspondence"
    FINANCIAL = "financial"
    AUDIT = "audit"
    UNKNOWN = "unknown"


class SemanticRole(str, Enum):
    """Effect role of an endorsement on the policy."""
    COVERAGE_MODIFIER = "coverage_modifier"
    EXCLUSION_MODIFIER = "exclusion_modifier"
    BOTH = "both"
    ADMINISTRATIVE_ONLY = "administrative_only"
    UNKNOWN = "unknown"


class CoverageEffect(str, Enum):
    """Specific semantic effects on coverage."""
    ADDS_COVERAGE = "adds_coverage"
    EXPANDS_COVERAGE = "expands_coverage"
    LIMITS_COVERAGE = "limits_coverage"
    RESTORES_COVERAGE = "restores_coverage"


class ExclusionEffect(str, Enum):
    """Specific semantic effects on exclusions."""
    INTRODUCES_EXCLUSION = "introduces_exclusion"
    NARROWS_EXCLUSION = "narrows_exclusion"
    REMOVES_EXCLUSION = "removes_exclusion"


class PageSignals(BaseModel):
    """Signals extracted from a single page.
    
    These signals are extracted without full OCR to enable fast page classification.
    """
    
    page_number: int = Field(..., description="1-indexed page number")
    top_lines: List[str] = Field(
        ..., 
        description="First few lines of the page or detected headings"
    )
    all_lines: List[str] = Field(
        default_factory=list,
        description="All lines of text for multi-section span detection"
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
    additional_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional structural metadata from Docling or other sources"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
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
    )


class TextSpan(BaseModel):
    """Represents a span of text within a page using line numbers."""
    
    start_line: int = Field(..., ge=1, description="Starting line number (1-indexed)")
    end_line: int = Field(..., ge=1, description="Ending line number (inclusive)")


class SectionSpan(BaseModel):
    """Represents a classified section block within a page."""
    
    section_type: PageType = Field(..., description="Type of section detected in span")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence for this span")
    span: Optional[TextSpan] = Field(None, description="Coordinates of the section in the text")
    reasoning: Optional[str] = Field(None, description="Reasoning for this span detection")
    semantic_role: Optional[SemanticRole] = Field(
        None, description="Semantic role of the span (for endorsements)"
    )
    coverage_effects: List[CoverageEffect] = Field(
        default_factory=list, description="Coverage effects for this span"
    )
    exclusion_effects: List[ExclusionEffect] = Field(
        default_factory=list, description="Exclusion effects for this span"
    )


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
    sections: List[SectionSpan] = Field(
        default_factory=list,
        description="List of detected sections within the page (for multi-section pages)"
    )
    semantic_role: Optional[SemanticRole] = Field(
        None, description="Semantic role of the page (mainly for endorsements)"
    )
    coverage_effects: List[CoverageEffect] = Field(
        default_factory=list, description="Coverage effects detected on this page"
    )
    exclusion_effects: List[ExclusionEffect] = Field(
        default_factory=list, description="Exclusion effects detected on this page"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "page_number": 12,
                "page_type": "declarations",
                "confidence": 0.98,
                "should_process": True,
                "duplicate_of": None,
                "reasoning": "Contains 'DECLARATIONS PAGE' and 'Policy Number' keywords"
            }
        }
    )


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
    # Document profile is added after PageManifest is created
    document_profile: Optional["DocumentProfile"] = Field(
        None,
        description="Document-level profile derived from page classifications (replaces Tier 1 LLM)"
    )
    page_section_map: Dict[int, str] = Field(
        default_factory=dict,
        description="Mapping of page numbers to section types for downstream processing"
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
    
    @property
    def document_type(self) -> Optional[str]:
        """Get document type from profile (for backward compatibility)."""
        if self.document_profile:
            return self.document_profile.document_type.value
        return None
    
    @property
    def section_boundaries(self) -> List["SectionBoundary"]:
        """Get section boundaries from profile (for backward compatibility)."""
        if self.document_profile:
            return self.document_profile.section_boundaries
        return []
    
    def get_pages_by_type(self, page_type: PageType) -> List[int]:
        """Get all page numbers of a specific type."""
        return [
            c.page_number 
            for c in self.classifications 
            if c.page_type == page_type
        ]
    
    def get_section_for_page(self, page_number: int) -> Optional[str]:
        """Get section type for a specific page number."""
        return self.page_section_map.get(page_number)
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "document_id": "550e8400-e29b-41d4-a716-446655440000",
                "total_pages": 120,
                "pages_to_process": [1, 2, 3, 10, 15, 80],
                "pages_skipped": [4, 5, 6, 7, 8, 9, 11, 12],
                "classifications": [],
                "document_profile": None,
                "page_section_map": {"1": "declarations", "2": "declarations"},
                "processing_ratio": 0.15,
                "cost_savings_estimate": 0.85
            }
        }
    )


class SectionBoundary(BaseModel):
    """Represents a detected section boundary within a document.
    
    Section boundaries are derived from page classifications and represent
    contiguous runs of pages belonging to the same section type.
    """
    
    section_type: PageType = Field(..., description="Type of section")
    start_page: int = Field(..., ge=1, description="Starting page number (1-indexed)")
    end_page: int = Field(..., ge=1, description="Ending page number (inclusive)")
    start_line: Optional[int] = Field(None, description="Starting line number within start_page")
    end_line: Optional[int] = Field(None, description="Ending line number within end_page")
    confidence: float = Field(
        ..., 
        ge=0.0, 
        le=1.0,
        description="Average confidence across pages in this section"
    )
    page_count: int = Field(..., ge=1, description="Number of pages in this section")
    anchor_text: Optional[str] = Field(
        None, 
        description="Text that triggered section detection (from first page)"
    )
    sub_section_type: Optional[str] = Field(
        None,
        description="Original granular section type if mapped to a broader category"
    )
    semantic_section: Optional[SemanticSection] = Field(
        None,
        description="High-level semantic section concept"
    )
    modifier_type: Optional[str] = Field(
        None,
        description="Modifier type for endorsements (adds, modifies, removes, etc.)"
    )
    endorsement_scope: Optional[str] = Field(
        None,
        description="Scope of an endorsement modifier (e.g., liability, property)"
    )
    extractable: bool = Field(
        True,
        description="Whether this section contains extractable insurance data"
    )
    semantic_role: Optional[SemanticRole] = Field(
        None, description="Semantic role of the section"
    )
    coverage_effects: List[CoverageEffect] = Field(
        default_factory=list, description="Coverage effects for this section"
    )
    exclusion_effects: List[ExclusionEffect] = Field(
        default_factory=list, description="Exclusion effects for this section"
    )
    effective_section_type: Optional[PageType] = Field(
        None,
        description="Effective section type for extraction (e.g., endorsement projected to coverages)"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context metadata for the section (e.g. parent policy section)"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "section_type": "declarations",
                "start_page": 1,
                "end_page": 5,
                "confidence": 0.95,
                "page_count": 5,
                "anchor_text": "DECLARATIONS PAGE",
                "sub_section_type": None
            }
        }
    )


class DocumentProfile(BaseModel):
    """Document-level profile aggregated from page classifications.
    
    This profile replaces Tier 1 LLM classification by deriving document type
    and section boundaries from rule-based page analysis. It provides all the
    context needed for downstream processing without additional LLM calls.
    """
    
    document_id: UUID = Field(..., description="Document UUID")
    document_type: DocumentType = Field(
        ..., 
        description="Classified document type derived from page type distribution"
    )
    document_subtype: Optional[str] = Field(
        None,
        description="Optional subtype (e.g., 'commercial_property' for policy)"
    )
    confidence: float = Field(
        ..., 
        ge=0.0, 
        le=1.0,
        description="Overall classification confidence"
    )
    section_boundaries: List[SectionBoundary] = Field(
        ..., 
        description="List of detected section boundaries"
    )
    page_section_map: Dict[int, str] = Field(
        ..., 
        description="Mapping of page numbers to section types"
    )
    section_type_distribution: Dict[str, int] = Field(
        default_factory=dict,
        description="Count of pages by normalized section type"
    )
    product_concepts: List[str] = Field(
        default_factory=list,
        description="List of core insurance concepts found (declarations, coverages, etc.)"
    )
    page_type_distribution: Dict[str, int] = Field(
        ..., 
        description="Count of pages by raw page type"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata from page analysis"
    )
    policy_form: Optional[str] = Field(None, description="Inferred policy form (e.g., commercial_auto)")
    carrier: Optional[str] = Field(None, description="Detected carrier name")
    semantic_capabilities: List[str] = Field(
        default_factory=list,
        description="List of semantic features enabled for this document type"
    )
    
    @property
    def section_count(self) -> int:
        """Number of distinct sections detected."""
        return len(self.section_boundaries)
    
    @property
    def has_declarations(self) -> bool:
        """Whether document has a declarations section."""
        if self.product_concepts:
            return "declarations" in self.product_concepts
        return any(
            sb.section_type == PageType.DECLARATIONS 
            for sb in self.section_boundaries
        )
    
    @property
    def has_coverages(self) -> bool:
        """Whether document has a coverages section."""
        if self.product_concepts:
            return "coverages" in self.product_concepts
        return any(
            sb.section_type == PageType.COVERAGES 
            for sb in self.section_boundaries
        )
    
    @property
    def has_endorsements(self) -> bool:
        """Whether document has an endorsements section."""
        if self.product_concepts:
            return "endorsements" in self.product_concepts
        return any(
            sb.section_type == PageType.ENDORSEMENT 
            for sb in self.section_boundaries
        )
    
    def get_section_pages(self, section_type: PageType) -> List[int]:
        """Get all page numbers belonging to a section type."""
        pages = []
        for boundary in self.section_boundaries:
            if boundary.section_type == section_type:
                pages.extend(range(boundary.start_page, boundary.end_page + 1))
        return pages
    
    def get_section_for_page(self, page_number: int) -> Optional[PageType]:
        """Get the section type for a specific page."""
        section_str = self.page_section_map.get(page_number)
        if section_str:
            try:
                return PageType(section_str)
            except ValueError:
                return PageType.UNKNOWN
        return None
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "document_id": "550e8400-e29b-41d4-a716-446655440000",
                "document_type": "policy",
                "document_subtype": "commercial_property",
                "confidence": 0.92,
                "section_boundaries": [
                    {
                        "section_type": "declarations",
                        "start_page": 1,
                        "end_page": 5,
                        "confidence": 0.95,
                        "page_count": 5
                    }
                ],
                "page_section_map": {
                    "1": "declarations",
                    "2": "declarations"
                },
                "page_type_distribution": {
                    "declarations": 5,
                    "coverages": 20,
                    "conditions": 10
                }
            }
        }
    )


# Rebuild models to resolve forward references
PageManifest.model_rebuild()
