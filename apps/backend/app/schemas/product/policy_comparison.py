"""Pydantic schemas for Policy Comparison workflow."""

from pydantic import BaseModel, Field, ConfigDict
from uuid import UUID
from typing import Optional, Literal, List, Dict, Any
from decimal import Decimal
from enum import Enum


# =====================================================
# Entity-Level Comparison Schemas
# =====================================================

class MatchType(str, Enum):
    """Classification of how two entities match across documents."""
    MATCH = "match"  # Exact or semantically equivalent match
    PARTIAL_MATCH = "partial_match"  # Similar but with differences
    ADDED = "added"  # Present in doc2 only
    REMOVED = "removed"  # Present in doc1 only
    UNCHANGED = "unchanged"  # Base entity not modified by endorsement
    TYPE_RECLASSIFIED = "type_reclassified"  # Same concept, different entity type
    NO_MATCH = "no_match"  # No corresponding entity found


class EntityType(str, Enum):
    """Type of insurance entity being compared."""
    COVERAGE = "coverage"
    EXCLUSION = "exclusion"


class EntityComparison(BaseModel):
    """Represents a comparison between two entities (coverages or exclusions) across documents."""
    model_config = ConfigDict(from_attributes=True)

    entity_type: EntityType = Field(..., description="Type of entity (coverage or exclusion)")
    match_type: MatchType = Field(..., description="Classification of the match")

    # Document 1 (base/expiring) entity data
    doc1_entity: Optional[Dict[str, Any]] = Field(
        None,
        description="Entity data from document 1 (None if ADDED)"
    )
    doc1_name: Optional[str] = Field(
        None,
        description="Entity name from document 1"
    )
    doc1_canonical_id: Optional[str] = Field(
        None,
        description="Canonical ID from document 1"
    )

    # Document 2 (endorsement/renewal) entity data
    doc2_entity: Optional[Dict[str, Any]] = Field(
        None,
        description="Entity data from document 2 (None if REMOVED)"
    )
    doc2_name: Optional[str] = Field(
        None,
        description="Entity name from document 2"
    )
    doc2_canonical_id: Optional[str] = Field(
        None,
        description="Canonical ID from document 2"
    )

    # Comparison details
    confidence: Decimal = Field(
        default=Decimal("0.0"),
        ge=0.0,
        le=1.0,
        description="Confidence score for the match (0.0-1.0)"
    )
    match_method: str = Field(
        default="llm_semantic",
        description="Method used for matching (canonical_id, llm_semantic, name_similarity)"
    )

    # Field-level differences (for PARTIAL_MATCH)
    field_differences: Optional[List[Dict[str, Any]]] = Field(
        None,
        description="List of field-level differences between matched entities"
    )

    reasoning: Optional[str] = Field(
        None,
        description="LLM-generated explanation of the match/difference"
    )
    severity: Literal["low", "medium", "high"] = Field(
        default="low",
        description="Severity of the difference (for PARTIAL_MATCH, ADDED, REMOVED)"
    )


class EntityComparisonSummary(BaseModel):
    """Summary of entity-level comparison results."""
    model_config = ConfigDict(from_attributes=True)

    total_coverages_doc1: int = Field(0, description="Total coverages in document 1")
    total_coverages_doc2: int = Field(0, description="Total coverages in document 2")
    total_exclusions_doc1: int = Field(0, description="Total exclusions in document 1")
    total_exclusions_doc2: int = Field(0, description="Total exclusions in document 2")

    coverage_matches: int = Field(0, description="Number of exact coverage matches")
    coverage_partial_matches: int = Field(0, description="Number of partial coverage matches")
    coverages_added: int = Field(0, description="Coverages added in document 2")
    coverages_removed: int = Field(0, description="Coverages removed from document 1")
    coverages_unchanged: int = Field(0, description="Base coverages not modified by endorsement")

    exclusion_matches: int = Field(0, description="Number of exact exclusion matches")
    exclusion_partial_matches: int = Field(0, description="Number of partial exclusion matches")
    exclusions_added: int = Field(0, description="Exclusions added in document 2")
    exclusions_removed: int = Field(0, description="Exclusions removed from document 1")
    exclusions_unchanged: int = Field(0, description="Base exclusions not modified by endorsement")

    entities_reclassified: int = Field(0, description="Entities classified as different types across documents")


class EntityComparisonResult(BaseModel):
    """Complete entity-level comparison result."""
    model_config = ConfigDict(from_attributes=True)

    workflow_id: UUID = Field(..., description="UUID of the workflow execution")
    doc1_id: UUID = Field(..., description="UUID of document 1 (base/expiring)")
    doc2_id: UUID = Field(..., description="UUID of document 2 (endorsement/renewal)")
    doc1_name: str = Field(..., description="Display name of document 1")
    doc2_name: str = Field(..., description="Display name of document 2")

    summary: EntityComparisonSummary = Field(..., description="Summary statistics")
    comparisons: List[EntityComparison] = Field(
        default_factory=list,
        description="List of entity comparisons"
    )

    overall_confidence: Decimal = Field(
        default=Decimal("0.0"),
        ge=0.0,
        le=1.0,
        description="Overall confidence score for the comparison"
    )
    overall_explanation: Optional[str] = Field(
        None,
        description="LLM-generated summary of all entity-level differences"
    )

    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (processing time, model used, etc.)"
    )


class PolicyComparisonRequest(BaseModel):
    """Request model for Policy Comparison workflow.
    
    Requires exactly 2 policy documents to compare.
    """
    model_config = ConfigDict(from_attributes=True)
    
    document_ids: list[UUID] = Field(
        ...,
        min_length=2,
        max_length=2,
        description="List of exactly 2 document UUIDs to compare (expiring vs renewal)",
        examples=[["uuid1", "uuid2"]]
    )
    policy_roles: Optional[list[Literal["expiring", "renewal"]]] = Field(
        None,
        min_length=2,
        max_length=2,
        description="Optional role labels for the documents (expiring, renewal)",
        examples=[["expiring", "renewal"]]
    )


class SectionProvenance(BaseModel):
    """Provenance information for a section alignment."""
    model_config = ConfigDict(from_attributes=True)
    
    doc1_section_id: UUID = Field(..., description="Section ID from first document")
    doc2_section_id: UUID = Field(..., description="Section ID from second document")
    doc1_page_range: Optional[dict] = Field(
        None, description="Page range in first document", examples=[{"start": 5, "end": 5}]
    )
    doc2_page_range: Optional[dict] = Field(
        None, description="Page range in second document", examples=[{"start": 6, "end": 6}]
    )


class SectionAlignment(BaseModel):
    """Represents aligned sections across two documents."""
    model_config = ConfigDict(from_attributes=True)
    
    section_type: str = Field(..., description="Type of section (declarations, coverages, etc.)")
    doc1_section_id: UUID = Field(..., description="Section ID from first document")
    doc2_section_id: UUID = Field(..., description="Section ID from second document")
    alignment_confidence: Decimal = Field(
        ..., 
        ge=0.0, 
        le=1.0, 
        description="Confidence score for the alignment (0.0-1.0)"
    )
    alignment_method: Optional[str] = Field(
        None, 
        description="Method used for alignment (direct, semantic, fuzzy_match)",
        examples=["direct"]
    )


class NumericDiff(BaseModel):
    """Represents a numeric change between two values."""
    model_config = ConfigDict(from_attributes=True)
    
    field_name: str = Field(..., description="Name of the numeric field")
    old_value: Optional[Decimal] = Field(None, description="Value in first document")
    new_value: Optional[Decimal] = Field(None, description="Value in second document")
    percent_change: Optional[Decimal] = Field(
        None, description="Percentage change (positive = increase, negative = decrease)"
    )
    absolute_change: Optional[Decimal] = Field(None, description="Absolute change in value")
    change_type: Literal["increase", "decrease", "no_change", "added", "removed"] = Field(
        ..., description="Type of change"
    )


class ComparisonChange(BaseModel):
    """Represents a single field change in the comparison."""
    model_config = ConfigDict(from_attributes=True)
    
    field_name: str = Field(..., description="Name of the changed field")
    section_type: str = Field(..., description="Section where change occurred")
    coverage_name: Optional[str] = Field(None, description="Coverage name if applicable")
    old_value: Optional[str | int | float | bool | Decimal | dict | list] = Field(None, description="Value in first document")
    new_value: Optional[str | int | float | bool | Decimal | dict | list] = Field(None, description="Value in second document")
    change_type: Literal[
        "increase", 
        "decrease", 
        "no_change", 
        "added", 
        "removed", 
        "modified", 
        "formatting_diff", 
        "sequential"
    ] = Field(..., description="Type of change")
    percent_change: Optional[Decimal] = Field(None, description="Percentage change for numeric fields")
    absolute_change: Optional[Decimal] = Field(None, description="Absolute change for numeric fields")
    severity: Literal["low", "medium", "high"] = Field(..., description="Severity of the change")
    delta_type: Optional[Literal["GAP", "ADVANTAGE", "NEGATIVE_CHANGE", "POSITIVE_CHANGE", "NEUTRAL"]] = Field(
        None, description="Strategic change type (GAP, ADVANTAGE, etc. for Proposals)"
    )
    delta_flag: Optional[Literal["NEGATIVE", "POSITIVE", "NEUTRAL"]] = Field(
        None, description="Sentiment flag for the change"
    )
    canonical_coverage_name: Optional[str] = Field(None, description="Standardized coverage name")
    provenance: SectionProvenance = Field(..., description="Source section information")
    reasoning: Optional[str] = Field(None, description="Detailed explanation of the difference")


class ComparisonSummary(BaseModel):
    """Summary statistics for the comparison."""
    model_config = ConfigDict(from_attributes=True)
    
    total_changes: int = Field(..., description="Total number of changes detected")
    high_severity_changes: int = Field(..., description="Number of high severity changes")
    medium_severity_changes: int = Field(..., description="Number of medium severity changes")
    low_severity_changes: int = Field(..., description="Number of low severity changes")
    sections_compared: int = Field(..., description="Number of sections compared")
    overall_confidence: Decimal = Field(
        ..., ge=0.0, le=1.0, description="Overall confidence score (0.0-1.0)"
    )


class PolicyComparisonResult(BaseModel):
    """Complete result payload for Policy Comparison workflow.
    
    This is stored in the workflow_outputs.result JSONB field.
    """
    model_config = ConfigDict(from_attributes=True)
    
    comparison_summary: ComparisonSummary = Field(..., description="Summary statistics")
    changes: list[ComparisonChange] = Field(..., description="List of all changes detected")
    section_alignments: list[SectionAlignment] = Field(..., description="Section alignment details")
    metadata: dict = Field(
        default_factory=dict,
        description="Additional metadata (workflow version, processing time, etc.)"
    )
    overall_explanation: Optional[str] = Field(None, description="Natural language summary of all changes")


class PolicyComparisonResponse(BaseModel):
    """Response model for Policy Comparison workflow execution."""
    model_config = ConfigDict(from_attributes=True)
    
    workflow_id: UUID = Field(..., description="UUID of the workflow execution")
    temporal_workflow_id: str = Field(..., description="Temporal workflow execution ID")
    status: str = Field(..., description="Workflow status (running, completed, failed)")
    message: str = Field(..., description="Human-readable status message")


class PolicyComparisonOutputResponse(BaseModel):
    """Response model for retrieving Policy Comparison output."""
    model_config = ConfigDict(from_attributes=True)
    
    workflow_id: UUID = Field(..., description="UUID of the workflow execution")
    workflow_name: str = Field(..., description="Name of the workflow")
    status: str = Field(
        ..., 
        description="Output status (COMPLETED, COMPLETED_WITH_WARNINGS, FAILED, NEEDS_REVIEW)"
    )
    confidence: Optional[Decimal] = Field(None, description="Overall confidence score (0.0-1.0)")
    result: PolicyComparisonResult = Field(..., description="Comparison result payload")
    metadata: Optional[dict] = Field(None, description="Additional context (warnings, HITL flags, etc.)")
    created_at: str = Field(..., description="Timestamp when output was created")
