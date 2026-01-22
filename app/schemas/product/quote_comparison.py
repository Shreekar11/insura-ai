"""Pydantic schemas for Quote Comparison workflow.

These schemas define the data contracts for quote comparison operations,
including canonical coverage normalization and comparison results.
"""

from pydantic import BaseModel, Field, ConfigDict
from uuid import UUID
from typing import Optional, Literal
from decimal import Decimal


class CoverageLimit(BaseModel):
    """Schema for normalized coverage limits (PRD Section 6.1)."""
    model_config = ConfigDict(from_attributes=True)
    
    type: Literal["absolute", "percentage"] = Field(
        ..., description="Whether the limit is an absolute value or percentage-based"
    )
    value: Decimal = Field(..., description="The limit value")
    derived_from: Optional[str] = Field(
        None, description="Source coverage if this is a derived/percentage limit"
    )


class CanonicalCoverage(BaseModel):
    """Canonical coverage model for normalized comparison (PRD Section 6.1)."""
    model_config = ConfigDict(from_attributes=True)
    
    canonical_coverage: str = Field(
        ..., description="Canonical coverage type (e.g., dwelling, liability)"
    )
    original_label: Optional[str] = Field(
        None, description="Original carrier-specific label"
    )
    category: Literal["property", "liability", "add_on"] = Field(
        ..., description="Coverage category"
    )
    is_base: bool = Field(
        ..., description="Whether this is a base coverage vs optional"
    )
    limit: CoverageLimit = Field(..., description="Normalized coverage limit")
    deductible: Optional[Decimal] = Field(
        None, description="Deductible amount"
    )
    conditions: list[str] = Field(
        default_factory=list, description="Applicable conditions"
    )
    optional: bool = Field(
        False, description="Whether this coverage is optional"
    )
    included: bool = Field(
        True, description="Whether included in base policy vs endorsed"
    )
    confidence: Decimal = Field(
        Decimal("1.0"), ge=0.0, le=1.0, description="Extraction confidence"
    )
    document_id: Optional[UUID] = Field(
        None, description="Source document ID"
    )


class CoverageQualityScore(BaseModel):
    """Coverage quality evaluation (PRD Section 7.4)."""
    model_config = ConfigDict(from_attributes=True)
    
    canonical_coverage: str = Field(..., description="Coverage being scored")
    coverage_presence: Decimal = Field(
        ..., description="Score for coverage being present"
    )
    limit_adequacy: Decimal = Field(
        ..., description="Score for limit adequacy"
    )
    deductible_penalty: Decimal = Field(
        ..., description="Penalty for high deductible"
    )
    exclusion_risk: Decimal = Field(
        ..., description="Penalty for exclusion exposure"
    )
    total_score: Decimal = Field(
        ..., description="Overall quality score"
    )


class QuoteComparisonRequest(BaseModel):
    """Request model for Quote Comparison workflow."""
    model_config = ConfigDict(from_attributes=True)
    
    document_ids: list[UUID] = Field(
        ...,
        min_length=2,
        max_length=2,
        description="List of exactly 2 quote document UUIDs to compare",
        examples=[["uuid1", "uuid2"]]
    )
    quote_roles: Optional[list[str]] = Field(
        None,
        min_length=2,
        max_length=2,
        description="Optional role labels for the quotes (carrier_a, carrier_b)",
        examples=[["carrier_a", "carrier_b"]]
    )


class QuoteProvenance(BaseModel):
    """Provenance information for a quote comparison alignment."""
    model_config = ConfigDict(from_attributes=True)
    
    quote1_section_id: UUID = Field(..., description="Section ID from first quote")
    quote2_section_id: UUID = Field(..., description="Section ID from second quote")
    quote1_page_range: Optional[dict] = Field(
        None, description="Page range in first quote", examples=[{"start": 1, "end": 2}]
    )
    quote2_page_range: Optional[dict] = Field(
        None, description="Page range in second quote", examples=[{"start": 1, "end": 2}]
    )


class CoverageComparisonRow(BaseModel):
    """A single row in the side-by-side coverage comparison matrix."""
    model_config = ConfigDict(from_attributes=True)
    
    canonical_coverage: str = Field(..., description="Canonical coverage name")
    category: str = Field(..., description="Coverage category")
    
    # Quote 1 values
    quote1_present: bool = Field(..., description="Whether coverage exists in quote 1")
    quote1_limit: Optional[Decimal] = Field(None, description="Limit in quote 1")
    quote1_deductible: Optional[Decimal] = Field(None, description="Deductible in quote 1")
    quote1_premium: Optional[Decimal] = Field(None, description="Premium in quote 1")
    quote1_included: Optional[bool] = Field(None, description="Included vs endorsed in quote 1")
    
    # Quote 2 values
    quote2_present: bool = Field(..., description="Whether coverage exists in quote 2")
    quote2_limit: Optional[Decimal] = Field(None, description="Limit in quote 2")
    quote2_deductible: Optional[Decimal] = Field(None, description="Deductible in quote 2")
    quote2_premium: Optional[Decimal] = Field(None, description="Premium in quote 2")
    quote2_included: Optional[bool] = Field(None, description="Included vs endorsed in quote 2")
    
    # Comparison indicators
    limit_difference: Optional[Decimal] = Field(None, description="Limit difference (q2 - q1)")
    limit_advantage: Optional[Literal["quote1", "quote2", "equal"]] = Field(
        None, description="Which quote has the higher limit"
    )
    deductible_advantage: Optional[Literal["quote1", "quote2", "equal"]] = Field(
        None, description="Which quote has the lower (better) deductible"
    )
    quality_score_quote1: Optional[Decimal] = Field(None, description="Quality score for quote 1")
    quality_score_quote2: Optional[Decimal] = Field(None, description="Quality score for quote 2")
    
    broker_note: Optional[str] = Field(
        None, description="Natural language reasoning for differences/similarities"
    )

    # ACORD / Requested baseline values
    requested_present: bool = Field(False, description="Whether coverage was requested in ACORD form")
    requested_limit: Optional[Decimal] = Field(None, description="Requested limit in ACORD form")
    requested_deductible: Optional[Decimal] = Field(None, description="Requested deductible in ACORD form")


class CoverageGap(BaseModel):
    """A coverage gap identified in the comparison."""
    model_config = ConfigDict(from_attributes=True)
    
    canonical_coverage: str = Field(..., description="Coverage that is missing")
    gap_type: Literal[
        "missing_in_quote1", 
        "missing_in_quote2", 
        "limit_inadequate", 
        "high_deductible",
        "missing_relative_to_acord",
        "limit_below_requested"
    ] = Field(
        ..., description="Type of gap"
    )
    severity: Literal["low", "medium", "high"] = Field(..., description="Gap severity")
    description: str = Field(..., description="Human-readable description")
    affected_quote: Optional[Literal["quote1", "quote2"]] = Field(
        None, description="Which quote is affected"
    )


class MaterialDifference(BaseModel):
    """A material difference worth highlighting to the broker."""
    model_config = ConfigDict(from_attributes=True)
    
    field_name: str = Field(..., description="Field that differs")
    section_type: str = Field(..., description="Section where difference occurs")
    coverage_name: Optional[str] = Field(None, description="Coverage name if applicable")
    quote1_value: Optional[str | int | float | bool | Decimal | dict | list] = Field(
        None, description="Value in quote 1"
    )
    quote2_value: Optional[str | int | float | bool | Decimal | dict | list] = Field(
        None, description="Value in quote 2"
    )
    change_type: Literal["increase", "decrease", "added", "removed", "modified", "identical"] = Field(
        ..., description="Type of change"
    )
    percent_change: Optional[Decimal] = Field(None, description="Percentage change for numeric fields")
    severity: Literal["low", "medium", "high"] = Field(..., description="Difference severity")
    broker_note: Optional[str] = Field(None, description="AI-generated note for broker")


class PricingAnalysis(BaseModel):
    """Pricing comparison analysis."""
    model_config = ConfigDict(from_attributes=True)
    
    quote1_total_premium: Decimal = Field(..., description="Total premium for quote 1")
    quote2_total_premium: Decimal = Field(..., description="Total premium for quote 2")
    premium_difference: Decimal = Field(..., description="Premium difference (q2 - q1)")
    premium_percent_change: Decimal = Field(..., description="Percentage change in premium")
    lower_premium_quote: Literal["quote1", "quote2", "equal"] = Field(
        ..., description="Which quote has lower premium"
    )
    fee_comparison: Optional[dict] = Field(None, description="Breakdown of fees if available")
    payment_terms_comparison: Optional[dict] = Field(None, description="Payment terms comparison")


class QuoteComparisonSummary(BaseModel):
    """Summary statistics for the quote comparison."""
    model_config = ConfigDict(from_attributes=True)
    
    total_coverages_compared: int = Field(..., description="Total coverages compared")
    coverage_gaps_count: int = Field(..., description="Number of coverage gaps identified")
    material_differences_count: int = Field(..., description="Number of material differences")
    high_severity_count: int = Field(..., description="Number of high severity issues")
    overall_confidence: Decimal = Field(
        ..., ge=0.0, le=1.0, description="Overall comparison confidence"
    )
    comparison_scope: Literal["full", "partial"] = Field(
        ..., description="Whether comparison was full or partial"
    )


class QuoteComparisonResult(BaseModel):
    """Complete result payload for Quote Comparison workflow.
    
    This is stored in the workflow_outputs.result JSONB field.
    """
    model_config = ConfigDict(from_attributes=True)
    
    comparison_summary: QuoteComparisonSummary = Field(..., description="Summary statistics")
    comparison_matrix: list[CoverageComparisonRow] = Field(
        ..., description="Side-by-side coverage comparison"
    )
    coverage_gaps: list[CoverageGap] = Field(
        ..., description="Identified coverage gaps"
    )
    material_differences: list[MaterialDifference] = Field(
        ..., description="Material differences worth noting"
    )
    pricing_analysis: PricingAnalysis = Field(..., description="Pricing comparison")
    broker_summary: Optional[str] = Field(
        None, description="Natural language summary for broker"
    )
    metadata: dict = Field(
        default_factory=dict,
        description="Additional metadata (workflow version, processing time)"
    )


class QuoteComparisonResponse(BaseModel):
    """Response model for Quote Comparison workflow execution."""
    model_config = ConfigDict(from_attributes=True)
    
    workflow_id: UUID = Field(..., description="UUID of the workflow execution")
    temporal_workflow_id: str = Field(..., description="Temporal workflow execution ID")
    status: str = Field(..., description="Workflow status (running, completed, failed)")
    message: str = Field(..., description="Human-readable status message")


class QuoteComparisonOutputResponse(BaseModel):
    """Response model for retrieving Quote Comparison output."""
    model_config = ConfigDict(from_attributes=True)
    
    workflow_id: UUID = Field(..., description="UUID of the workflow execution")
    workflow_name: str = Field(..., description="Name of the workflow")
    status: str = Field(
        ..., description="Output status (COMPLETED, COMPLETED_WITH_WARNINGS, FAILED, NEEDS_REVIEW)"
    )
    confidence: Optional[Decimal] = Field(None, description="Overall confidence score")
    result: QuoteComparisonResult = Field(..., description="Comparison result payload")
    metadata: Optional[dict] = Field(None, description="Additional context (warnings, HITL flags)")
    created_at: str = Field(..., description="Timestamp when output was created")
