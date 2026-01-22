"""
Neo4j Graph Schema Definitions.

This module defines the Pydantic models for nodes and relationships in the
Insura AI knowledge graph, aligned with GraphRAG, vector indexing, and
industry-standard insurance knowledge graphs.
"""

from typing import Optional, List
from enum import Enum
from datetime import date
from pydantic import BaseModel, Field


# Base Models
class GraphNode(BaseModel):
    """
    Base model for all graph nodes.

    `id` MUST be a stable internal identifier and MUST align 1:1 with
    vector embedding entity_id values.
    """
    id: str = Field(
        ...,
        description="Stable internal ID used by vector embeddings (e.g., policy_POL123, coverage_windstorm)"
    )


class GraphRelationship(BaseModel):
    """Base model for graph relationships."""
    pass


# Enums
class OrganizationRole(str, Enum):
    """Roles an organization can play in the insurance context."""
    INSURED = "insured"
    ADDITIONAL_INSURED = "additional_insured"
    BROKER = "broker"
    CARRIER = "carrier"
    AGENT = "agent"
    UNDERWRITER = "underwriter"


class ConditionType(str, Enum):
    """Types of policy conditions."""
    LOSS = "loss"
    CLAIMS = "claims"
    GENERAL = "general"
    PROPERTY = "property"


# Node Models
class PolicyNode(GraphNode):
    """Represents an insurance policy."""
    policy_number: str
    policy_type: Optional[str] = None
    policy_form: Optional[str] = None
    status: Optional[str] = None

    effective_date: Optional[date] = None
    expiration_date: Optional[date] = None
    policy_term: Optional[str] = None

    total_premium: Optional[float] = None
    base_premium: Optional[float] = None
    rate_per_100: Optional[float] = None

    source_document_id: Optional[str] = None


class OrganizationNode(GraphNode):
    """Represents an organization (insured, broker, carrier, etc.)."""
    name: str
    role: OrganizationRole
    address: Optional[str] = None


class CoverageNode(GraphNode):
    """
    Represents a specific coverage.

    Coverage nodes are core GraphRAG entry points and must contain
    descriptive text in addition to numeric attributes.
    """
    name: str
    coverage_type: Optional[str] = None
    coverage_part: Optional[str] = None

    description: Optional[str] = None

    per_occurrence_limit: Optional[float] = None
    aggregate_limit: Optional[float] = None
    deductible_amount: Optional[float] = None
    deductible_type: Optional[str] = None
    waiting_period: Optional[str] = None
    coinsurance: Optional[str] = None
    valuation_method: Optional[str] = None

    included: Optional[bool] = None

    source_section: Optional[str] = "coverages"
    source_chunk_id: Optional[str] = None


class ConditionNode(GraphNode):
    """
    Represents a policy condition.

    Conditions are text-heavy and essential for claims and FNOL GraphRAG.
    """
    title: str
    condition_type: Optional[ConditionType] = None
    description: str

    applies_to: Optional[str] = None
    requirements: Optional[List[str]] = None
    consequences: Optional[List[str]] = None

    source_section: Optional[str] = "conditions"
    source_chunk_id: Optional[str] = None


class EndorsementNode(GraphNode):
    """Represents a policy endorsement."""
    endorsement_number: Optional[str] = None
    title: str
    description: Optional[str] = None
    effective_date: Optional[date] = None

    source_section: Optional[str] = "endorsements"
    source_chunk_id: Optional[str] = None


class LocationNode(GraphNode):
    """Represents a physical location or property."""
    location_id: Optional[str] = None
    address: str

    construction_type: Optional[str] = None
    occupancy: Optional[str] = None
    year_built: Optional[int] = None
    number_of_stories: Optional[int] = None
    sprinklered: Optional[bool] = None

    distance_to_coast: Optional[float] = None
    flood_zone: Optional[str] = None

    building_value: Optional[float] = None
    contents_value: Optional[float] = None
    bi_value: Optional[float] = None
    tiv: Optional[float] = None

    source_section: Optional[str] = "schedule_of_values"
    source_chunk_id: Optional[str] = None


class ClaimNode(GraphNode):
    """Represents an insurance claim."""
    claim_number: str
    cause_of_loss: Optional[str] = None
    status: Optional[str] = None

    loss_date: Optional[date] = None
    reported_date: Optional[date] = None

    paid_amount: Optional[float] = None
    incurred_amount: Optional[float] = None
    reserve_amount: Optional[float] = None

    source_section: Optional[str] = "loss_run"
    source_chunk_id: Optional[str] = None


class VehicleNode(GraphNode):
    """Represents an insured vehicle."""
    vin: Optional[str] = None
    year: Optional[int] = None
    make: Optional[str] = None
    model: Optional[str] = None


class DriverNode(GraphNode):
    """Represents an insured driver."""
    name: str
    date_of_birth: Optional[date] = None
    license_number: Optional[str] = None
    violations: Optional[int] = None
    accidents: Optional[int] = None


class DefinitionNode(GraphNode):
    """Represents a defined term in the policy glossary."""
    term: str
    definition_text: str

    source_section: Optional[str] = "definitions"
    source_chunk_id: Optional[str] = None


class EvidenceNode(GraphNode):
    """
    Represents raw text evidence supporting an entity or relationship.
    Evidence nodes are mandatory for explainable GraphRAG.
    """
    document_id: str
    chunk_id: str
    quote: str
    start_offset: Optional[int] = None
    end_offset: Optional[int] = None


# Relationship Types
class RelationshipType(str, Enum):
    """Valid relationship types for the insurance knowledge graph."""

    # Policy-centric
    HAS_INSURED = "HAS_INSURED"
    HAS_ADDITIONAL_INSURED = "HAS_ADDITIONAL_INSURED"
    BROKERED_BY = "BROKERED_BY"
    ISSUED_BY = "ISSUED_BY"

    # Identity / Canonicalization
    SAME_AS = "SAME_AS"

    # Coverage
    HAS_COVERAGE = "HAS_COVERAGE"
    APPLIES_TO = "APPLIES_TO"
    MODIFIED_BY = "MODIFIED_BY"
    EXCLUDES = "EXCLUDES"
    SUBJECT_TO = "SUBJECT_TO"

    # Conditions
    HAS_CONDITION = "HAS_CONDITION"

    # Location
    HAS_LOCATION = "HAS_LOCATION"

    # Claims
    HAS_CLAIM = "HAS_CLAIM"
    OCCURRED_AT = "OCCURRED_AT"

    # Auto
    HAS_VEHICLE = "HAS_VEHICLE"
    OPERATED_BY = "OPERATED_BY"

    # Definitions
    DEFINED_IN = "DEFINED_IN"

    # Evidence
    SUPPORTED_BY = "SUPPORTED_BY"
