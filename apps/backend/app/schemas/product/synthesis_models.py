"""Pydantic schemas for coverage/exclusion synthesis output.

These schemas define the FurtherAI-style coverage-centric and exclusion-centric
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


class EffectiveExclusion(BaseModel):
    """Exclusion-centric output showing effective state after endorsements applied."""

    model_config = ConfigDict(extra="allow")

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
