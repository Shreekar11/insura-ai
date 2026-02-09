"""Pydantic schemas for coverage/exclusion synthesis output.

These schemas define the coverage-centric and exclusion-centric
output format that transforms endorsement modifications into effective terms.
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from enum import Enum


class SynthesisMethod(str, Enum):
    """Method used to synthesize effective coverages/exclusions."""
    ENDORSEMENT_ONLY = "endorsement_only"
    BASE_COVERAGE_MERGE = "base_coverage_merge"
    LLM_INFERENCE = "llm_inference"
    TWO_DOCUMENT_MERGE = "two_document_merge"


class DocumentCategory(str, Enum):
    """Category of insurance document."""
    BASE_FORM = "base_form"
    ENDORSEMENT_PACKAGE = "endorsement_package"
    CERTIFICATE = "certificate"
    DECLARATIONS = "declarations"
    SCHEDULE = "schedule"
    UNKNOWN = "unknown"


class BaseFormType(str, Enum):
    """Standard ISO base form types."""
    CA_00_01 = "CA 00 01"  # Business Auto Coverage Form
    CG_00_01 = "CG 00 01"  # Commercial General Liability Coverage Form
    CP_00_10 = "CP 00 10"  # Building and Personal Property Coverage Form
    WC_00_00 = "WC 00 00"  # Workers Compensation and Employers Liability
    CP_00_30 = "CP 00 30"  # Business Income Coverage Form
    IM_00_00 = "IM 00 00"  # Inland Marine
    UNKNOWN = "unknown"


class DocumentTypeResult(BaseModel):
    """Result of document type classification."""

    model_config = ConfigDict(extra="allow")

    category: DocumentCategory = Field(
        ...,
        description="Primary document category"
    )
    form_id: Optional[str] = Field(
        None,
        description="ISO form ID if detected (e.g., 'CA 00 01')"
    )
    form_name: Optional[str] = Field(
        None,
        description="Human-readable form name"
    )
    form_edition_date: Optional[str] = Field(
        None,
        description="Form edition date (e.g., '10 13' for October 2013)"
    )
    endorsement_list: Optional[List[str]] = Field(
        None,
        description="List of endorsement numbers if endorsement package"
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Classification confidence"
    )
    detected_patterns: Optional[List[str]] = Field(
        None,
        description="Patterns that led to classification"
    )


class StandardProvision(BaseModel):
    """A standard coverage or exclusion from a base form."""

    model_config = ConfigDict(extra="allow")

    provision_name: str = Field(..., description="Name of the provision")
    provision_type: str = Field(
        ...,
        description="Type: coverage | exclusion | condition | definition"
    )
    provision_number: Optional[str] = Field(
        None,
        description="Numbered designation (e.g., 'A', 'B.1', 'II.A')"
    )
    source_form: str = Field(..., description="Source form ID")
    form_section: Optional[str] = Field(
        None,
        description="Section in the form (e.g., 'SECTION II')"
    )
    description: Optional[str] = Field(
        None,
        description="Description of the provision"
    )
    verbatim_text: Optional[str] = Field(
        None,
        description="Verbatim text from the form"
    )
    sub_provisions: Optional[List[str]] = Field(
        None,
        description="Sub-items under this provision"
    )
    confidence: float = Field(default=0.95, ge=0.0, le=1.0)


class BaseFormExtractionResult(BaseModel):
    """Result of extracting provisions from a base form."""

    model_config = ConfigDict(extra="allow")

    form_id: str = Field(..., description="ISO form ID")
    form_name: str = Field(..., description="Human-readable form name")
    form_edition_date: Optional[str] = Field(None, description="Edition date")
    coverages: List[StandardProvision] = Field(
        default_factory=list,
        description="Standard coverages from the form"
    )
    exclusions: List[StandardProvision] = Field(
        default_factory=list,
        description="Standard exclusions from the form"
    )
    conditions: List[StandardProvision] = Field(
        default_factory=list,
        description="Standard conditions from the form"
    )
    definitions: List[StandardProvision] = Field(
        default_factory=list,
        description="Standard definitions from the form"
    )
    extraction_confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class EffectiveTerm(BaseModel):
    """A single effective term within a coverage."""
    term_name: str = Field(..., description="Name of the coverage term")
    status: str = Field(..., description="Covered | Excluded | Modified | Expanded | Restricted")
    details: Optional[str] = Field(None, description="Additional details about the term")
    conditions: Optional[List[str]] = Field(None, description="Conditions that apply")
    source_endorsement: Optional[str] = Field(None, description="Endorsement that established this term")


class EffectiveCoverage(BaseModel):
    """Coverage-centric output showing effective state after endorsements applied."""

    model_config = ConfigDict(extra="allow")

    canonical_id: Optional[str] = Field(
        None,
        description="Canonical identifier for semantic matching across documents (e.g., 'coverage:liability:auto')"
    )
    coverage_name: str = Field(..., description="Name of the coverage (e.g., 'Business Auto Liability')")
    coverage_type: Optional[str] = Field(None, description="Type: Liability | Property | Auto | Workers Comp")
    effective_terms: Dict[str, str] = Field(
        default_factory=dict,
        description="Map of term names to their effective state (e.g., {'hired_auto': 'Covered'})"
    )
    detailed_terms: Optional[List[EffectiveTerm]] = Field(
        None,
        description="Detailed term breakdown with conditions"
    )
    limits: Optional[Dict[str, Any]] = Field(None, description="Effective limits after modifications")
    deductibles: Optional[Dict[str, Any]] = Field(None, description="Effective deductibles")
    sources: List[str] = Field(
        default_factory=list,
        description="Source documents/endorsements for this coverage"
    )
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reasoning: Optional[str] = Field(None, description="Explanation of how this coverage was synthesized")

    # New fields for two-document extraction pipeline
    description: Optional[str] = Field(
        None,
        description="Human-readable description of the coverage"
    )
    source_form: Optional[str] = Field(
        None,
        description="Source form ID (e.g., 'CA 00 01', 'CG 00 01')"
    )
    is_standard_provision: bool = Field(
        default=False,
        description="Whether this coverage comes from a base/standard form"
    )
    is_modified: bool = Field(
        default=False,
        description="Whether this coverage has been modified by endorsement"
    )
    modification_details: Optional[str] = Field(
        None,
        description="Description of how the coverage was modified by endorsement"
    )
    form_section: Optional[str] = Field(
        None,
        description="Section reference in the source form (e.g., 'SECTION II', 'SECTION III')"
    )

    # Citation fields for source mapping (FR-1, FR-4)
    citation_id: Optional[str] = Field(
        None,
        description="Reference to citation record for PDF source mapping"
    )
    page_numbers: Optional[List[int]] = Field(
        None,
        description="Page numbers where this coverage is defined (1-indexed)"
    )
    source_text: Optional[str] = Field(
        None,
        description="Verbatim source text from policy document"
    )
    clause_reference: Optional[str] = Field(
        None,
        description="Clause reference e.g., 'SECTION II - COVERAGES, A.1'"
    )


class EffectiveExclusion(BaseModel):
    """Exclusion-centric output showing effective state after endorsements applied."""

    model_config = ConfigDict(extra="allow")

    canonical_id: Optional[str] = Field(
        None,
        description="Canonical identifier for semantic matching across documents (e.g., 'exclusion:pollution')"
    )
    exclusion_name: str = Field(..., description="Name of the exclusion")
    effective_state: str = Field(
        ...,
        description="Excluded | Partially Excluded | Carved Back | Removed"
    )
    scope: Optional[str] = Field(None, description="What the exclusion applies to")
    carve_backs: Optional[List[str]] = Field(
        None,
        description="Exceptions/carve-backs that restore coverage"
    )
    conditions: Optional[List[str]] = Field(
        None,
        description="Conditions under which exclusion applies"
    )
    impacted_coverages: Optional[List[str]] = Field(
        None,
        description="Coverages affected by this exclusion"
    )
    sources: List[str] = Field(
        default_factory=list,
        description="Source documents/endorsements"
    )
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    severity: Optional[str] = Field(None, description="Material | Minor | Administrative")
    reasoning: Optional[str] = Field(None, description="Explanation of exclusion state")

    # New fields for two-document extraction pipeline
    exclusion_number: Optional[str] = Field(
        None,
        description="Numbered designation of the exclusion (e.g., 'B.1', 'B.2')"
    )
    description: Optional[str] = Field(
        None,
        description="Human-readable description of the exclusion"
    )
    source_form: Optional[str] = Field(
        None,
        description="Source form ID (e.g., 'CA 00 01', 'CG 00 01')"
    )
    is_standard_provision: bool = Field(
        default=True,
        description="Whether this exclusion comes from a base/standard form"
    )
    is_modified: bool = Field(
        default=False,
        description="Whether this exclusion has been modified by endorsement"
    )
    modification_details: Optional[str] = Field(
        None,
        description="Description of how the exclusion was modified by endorsement"
    )
    form_section: Optional[str] = Field(
        None,
        description="Section reference in the source form (e.g., 'SECTION II')"
    )

    # Citation fields for source mapping (FR-1, FR-4)
    citation_id: Optional[str] = Field(
        None,
        description="Reference to citation record for PDF source mapping"
    )
    page_numbers: Optional[List[int]] = Field(
        None,
        description="Page numbers where this exclusion is defined (1-indexed)"
    )
    source_text: Optional[str] = Field(
        None,
        description="Verbatim source text from policy document"
    )
    clause_reference: Optional[str] = Field(
        None,
        description="Clause reference e.g., 'SECTION II - EXCLUSIONS, B.1'"
    )


class SynthesisResult(BaseModel):
    """Complete synthesis result containing effective coverages and exclusions."""

    model_config = ConfigDict(extra="allow")

    effective_coverages: List[EffectiveCoverage] = Field(default_factory=list)
    effective_exclusions: List[EffectiveExclusion] = Field(default_factory=list)
    overall_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    synthesis_method: str = Field(
        default=SynthesisMethod.ENDORSEMENT_ONLY.value,
        description="Method used: endorsement_only | base_coverage_merge | llm_inference"
    )
    fallback_used: bool = Field(
        default=False,
        description="Whether LLM inference fallback was triggered"
    )
    source_endorsement_count: int = Field(default=0)
    warnings: Optional[List[str]] = Field(None, description="Any warnings during synthesis")
