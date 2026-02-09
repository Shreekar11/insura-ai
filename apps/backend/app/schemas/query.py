"""
GraphRAG Retrieval Schema Definitions

This module contains all Pydantic models for the GraphRAG retrieval pipeline,
organized by stage:
- Stage 1: Query Understanding & Intent Classification
- Stage 2: Vector-Based Retrieval
- Stage 3: Graph-Based Context Expansion
- Stage 4: Context Assembly
- Stage 5: LLM Response Generation
- API: Request/Response models
"""

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# Query Understanding Models
class ExtractedQueryEntities(BaseModel):
    """Entities extracted from user query using regex + LLM hybrid approach."""

    policy_numbers: list[str] = Field(
        default_factory=list,
        description="Policy numbers mentioned in query (e.g., 'POL-12345')",
    )
    coverage_types: list[str] = Field(
        default_factory=list,
        description="Coverage types (e.g., 'general liability', 'property')",
    )
    entity_names: list[str] = Field(
        default_factory=list,
        description="Insured names, carrier names, broker names",
    )
    dates: list[str] = Field(
        default_factory=list, description="Effective dates, loss dates, policy periods"
    )
    amounts: list[str] = Field(
        default_factory=list, description="Limits, deductibles, premiums, claim amounts"
    )
    locations: list[str] = Field(
        default_factory=list, description="Addresses, states, cities"
    )
    section_hints: list[str] = Field(
        default_factory=list,
        description="Section references (e.g., 'exclusions', 'endorsements')",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "policy_numbers": ["POL-CA-00-01"],
                "coverage_types": ["general liability", "property"],
                "entity_names": ["HARBOR COVE APARTMENTS"],
                "dates": ["2024-01-01"],
                "amounts": ["$1,000,000"],
                "locations": ["California"],
                "section_hints": ["coverages", "exclusions"],
            }
        }


class WorkflowContext(BaseModel):
    """Context fetched from PostgreSQL for the workflow."""

    workflow_id: UUID
    sections: list[dict[str, Any]] = Field(
        default_factory=list,
        description="StepSectionOutput records (Coverages, Exclusions, etc.)",
    )
    entities: list[dict[str, Any]] = Field(
        default_factory=list, description="StepEntityOutput records (Insured, Carrier)"
    )
    document_ids: list[UUID] = Field(
        default_factory=list, description="Document IDs in this workflow"
    )
    document_count: int = Field(default=0, description="Total documents in workflow")

    @field_validator("document_count", mode="before")
    @classmethod
    def set_document_count(cls, v: int, info) -> int:
        """Auto-set document count from document_ids if not provided."""
        if v == 0 and "document_ids" in info.data:
            return len(info.data["document_ids"])
        return v


class QueryPlan(BaseModel):
    """Complete query plan produced by Stage 1."""

    original_query: str = Field(description="Raw user query")
    intent: Literal["QA", "ANALYSIS", "AUDIT"] = Field(
        description="Classified intent type"
    )
    traversal_depth: int = Field(
        ge=1, le=5, description="Graph traversal depth (1-5 hops)"
    )
    extracted_entities: ExtractedQueryEntities
    expanded_queries: list[str] = Field(
        description="Query variations for multi-query retrieval"
    )
    workflow_context: WorkflowContext

    # Derived filters
    target_document_ids: list[UUID] | None = Field(
        default=None, description="None = all workflow docs"
    )
    section_type_filters: list[str] = Field(
        default_factory=list, description="Section types to prioritize"
    )
    entity_type_filters: list[str] = Field(
        default_factory=list, description="Entity types to prioritize"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "original_query": "What is my property deductible?",
                "intent": "QA",
                "traversal_depth": 1,
                "extracted_entities": {
                    "policy_numbers": [],
                    "coverage_types": ["property"],
                    "entity_names": [],
                    "dates": [],
                    "amounts": [],
                    "locations": [],
                    "section_hints": ["coverages", "declarations"],
                },
                "expanded_queries": [
                    "What is my property deductible?",
                    "What is my property self-insured retention?",
                    "What is my property SIR?",
                ],
                "workflow_context": {
                    "workflow_id": "123e4567-e89b-12d3-a456-426614174000",
                    "sections": [],
                    "entities": [],
                    "document_ids": [],
                    "document_count": 2,
                },
                "target_document_ids": None,
                "section_type_filters": ["coverages", "declarations"],
                "entity_type_filters": ["coverage"],
            }
        }


# Vector Retrieval Models

class VectorSearchResult(BaseModel):
    """Result from vector similarity search."""

    embedding_id: UUID = Field(description="VectorEmbedding record ID")
    document_id: UUID
    chunk_id: UUID | None = Field(default=None, description="Source chunk ID if entity-level embedding")
    canonical_entity_id: UUID | None = Field(
        default=None, description="FK to canonical_entities table"
    )
    entity_id: str | None = Field(
        default=None, description="Positional entity_id (e.g., 'coverages_cov_0')"
    )
    content: str = Field(description="Full text content of the embedding")
    section_type: str = Field(description="Section type (e.g., 'coverages')")
    entity_type: str | None = Field(
        default=None, description="Entity type (e.g., 'coverage', 'exclusion')"
    )

    # Scoring
    similarity_score: float = Field(
        ge=0.0, le=1.0, description="Cosine similarity score"
    )
    final_score: float = Field(
        ge=0.0, description="Final score after reranking boosts"
    )

    # Provenance
    document_name: str = Field(description="Source document filename")
    page_numbers: list[int] = Field(
        default_factory=list, description="Page numbers where content appears"
    )
    page_range: dict[str, int] | None = Field(
        default=None, description="Page range metadata (start, end)"
    )
    effective_date: date | None = Field(
        default=None, description="Policy effective date for recency boost"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "embedding_id": "123e4567-e89b-12d3-a456-426614174001",
                "document_id": "123e4567-e89b-12d3-a456-426614174000",
                "chunk_id": "123e4567-e89b-12d3-a456-426614174002",
                "canonical_entity_id": "123e4567-e89b-12d3-a456-426614174003",
                "entity_id": "coverages_cov_0",
                "content": "Property deductible: $5,000 per occurrence",
                "section_type": "coverages",
                "entity_type": "coverage",
                "similarity_score": 0.89,
                "final_score": 0.96,
                "document_name": "POL_CA_00_01.pdf",
                "page_numbers": [3, 4],
                "page_range": {"start": 3, "end": 4},
                "effective_date": "2024-01-01",
            }
        }


# Graph Expansion Models

class GraphNode(BaseModel):
    """Neo4j graph node representation."""

    node_id: str = Field(description="Neo4j internal node ID")
    entity_id: str = Field(
        description="Positional entity_id or canonical_key for mapping"
    )
    canonical_entity_id: UUID | None = Field(
        default=None, description="FK to canonical_entities (if available)"
    )
    entity_type: str = Field(description="Entity type (Coverage, Exclusion, etc.)")
    labels: list[str] = Field(description="Neo4j node labels")
    properties: dict[str, Any] = Field(
        default_factory=dict, description="All node properties"
    )
    workflow_id: UUID = Field(description="Workflow scope")

    @classmethod
    def from_neo4j(cls, record: dict[str, Any]) -> "GraphNode":
        """Construct from Neo4j query result."""
        node = record.get("n") or record.get("node")
        labels = record.get("labels", [])

        return cls(
            node_id=str(node.id),
            entity_id=node.get("entity_id") or node.get("id"),
            canonical_entity_id=node.get("canonical_entity_id"),
            entity_type=node.get("entity_type", labels[0] if labels else "Unknown"),
            labels=labels,
            properties=dict(node),
            workflow_id=node.get("workflow_id"),
        )


class GraphTraversalResult(BaseModel):
    """Result from graph traversal with relationship context."""

    node_id: str = Field(description="Neo4j node ID")
    entity_id: str = Field(description="Entity identifier")
    canonical_entity_id: UUID | None = Field(default=None)
    entity_type: str = Field(description="Entity type label")
    labels: list[str] = Field(description="All Neo4j labels")
    properties: dict[str, Any] = Field(
        default_factory=dict, description="Node properties"
    )

    # Traversal metadata
    distance: int = Field(ge=0, description="Hops from start node")
    relationship_chain: list[str] = Field(
        description="Relationship types in path (e.g., ['HAS_COVERAGE', 'MODIFIED_BY'])"
    )
    relevance_score: float = Field(
        default=0.0, description="Computed relevance score"
    )

    # Provenance
    document_id: UUID | None = Field(default=None)
    source_section: str | None = Field(
        default=None, description="Section where entity was extracted"
    )

    @classmethod
    def from_neo4j(cls, record: dict[str, Any]) -> "GraphTraversalResult":
        """Construct from Neo4j traversal query result."""
        related = record.get("related")
        distance = record.get("distance", 0)
        relationship_chain = record.get("relationship_chain", [])

        return cls(
            node_id=str(related.id),
            entity_id=related.get("entity_id") or related.get("id"),
            canonical_entity_id=related.get("canonical_entity_id"),
            entity_type=related.get("entity_type", "Unknown"),
            labels=record.get("labels", []),
            properties=dict(related),
            distance=distance,
            relationship_chain=relationship_chain,
            relevance_score=0.0,  # Will be computed by relevance filter
            document_id=related.get("document_id"),
            source_section=related.get("source_section"),
        )

    class Config:
        json_schema_extra = {
            "example": {
                "node_id": "neo4j_node_123",
                "entity_id": "755dc853d07aa2c0...",
                "canonical_entity_id": "123e4567-e89b-12d3-a456-426614174000",
                "entity_type": "Coverage",
                "labels": ["Coverage"],
                "properties": {
                    "name": "General Liability",
                    "limit": "$1,000,000",
                    "deductible": "$5,000",
                },
                "distance": 1,
                "relationship_chain": ["HAS_COVERAGE"],
                "relevance_score": 0.85,
                "document_id": "123e4567-e89b-12d3-a456-426614174001",
                "source_section": "coverages",
            }
        }


# Context Assembly Models

class MergedResult(BaseModel):
    """Merged result from vector + graph sources."""

    source: Literal["vector", "graph", "both"] = Field(
        description="Origin of this result"
    )
    content: str = Field(description="Full text content")
    summary: str | None = Field(default=None, description="LLM-generated summary")

    # Entity metadata
    entity_type: str | None = Field(default=None)
    entity_id: str | None = Field(default=None)
    canonical_entity_id: UUID | None = Field(default=None)
    section_type: str | None = Field(default=None)

    # Scoring
    relevance_score: float = Field(description="Combined relevance score")
    distance: int | None = Field(default=None, description="Graph distance (if from graph)")

    # Provenance
    document_id: UUID
    document_name: str
    page_numbers: list[int] = Field(default_factory=list)
    relationship_path: list[str] | None = Field(
        default=None, description="Graph relationship chain"
    )
    citation_id: str | None = Field(
        default=None, description="Citation ID (e.g. '[1]') assigned during context assembly"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "source": "both",
                "content": "Property Coverage: $2,000,000 limit, $5,000 deductible",
                "summary": None,
                "entity_type": "coverage",
                "entity_id": "coverages_cov_0",
                "canonical_entity_id": "123e4567-e89b-12d3-a456-426614174000",
                "section_type": "coverages",
                "relevance_score": 0.96,
                "distance": 0,
                "document_id": "123e4567-e89b-12d3-a456-426614174001",
                "document_name": "POL_CA_00_01.pdf",
                "page_numbers": [3, 4],
                "relationship_path": None,
            }
        }


class ProvenanceEntry(BaseModel):
    """Provenance information for citation tracking."""

    document_name: str
    document_id: UUID
    page_numbers: list[int] = Field(default_factory=list)
    section_type: str | None = Field(default=None)
    relationship_path: list[str] | None = Field(default=None)

    class Config:
        json_schema_extra = {
            "example": {
                "document_name": "POL_CA_00_01.pdf",
                "document_id": "123e4567-e89b-12d3-a456-426614174000",
                "page_numbers": [3, 4],
                "section_type": "coverages",
                "relationship_path": ["HAS_COVERAGE", "MODIFIED_BY"],
            }
        }


class ContextPayload(BaseModel):
    """Hierarchical context payload for LLM consumption."""

    full_text_results: list[MergedResult] = Field(
        description="Top-N results with full content"
    )
    summary_results: list[MergedResult] = Field(
        description="Additional results with summaries"
    )
    total_results: int = Field(description="Total results before truncation")
    token_count: int = Field(description="Total tokens in context")
    provenance_index: dict[str, ProvenanceEntry] = Field(
        description="Citation ID -> provenance mapping (e.g., '[1]' -> ProvenanceEntry)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "full_text_results": [],  # 5 results with full text
                "summary_results": [],  # 10 results with summaries
                "total_results": 15,
                "token_count": 7500,
                "provenance_index": {
                    "[1]": {
                        "document_name": "POL_CA_00_01.pdf",
                        "document_id": "123e4567-e89b-12d3-a456-426614174000",
                        "page_numbers": [3],
                        "section_type": "coverages",
                        "relationship_path": None,
                    }
                },
            }
        }


# Response Generation Models

class GeneratedResponse(BaseModel):
    """LLM-generated response with context."""

    answer: str = Field(description="LLM-generated answer with inline citations")
    provenance: dict[str, ProvenanceEntry] = Field(
        description="Citation ID to provenance mapping"
    )
    context_used: ContextPayload = Field(description="Context that was provided to LLM")

    class Config:
        json_schema_extra = {
            "example": {
                "answer": "Your property deductible is $5,000 per occurrence [1]. This applies to all covered property damage claims.",
                "provenance": {
                    "[1]": {
                        "document_name": "POL_CA_00_01.pdf",
                        "document_id": "123e4567-e89b-12d3-a456-426614174000",
                        "page_numbers": [3],
                        "section_type": "coverages",
                        "relationship_path": None,
                    }
                },
                "context_used": {},  # ContextPayload
            }
        }


class SourceCitation(BaseModel):
    """Structured citation for a source document."""

    citation_id: str = Field(description="Citation ID used in answer (e.g., '1')")
    document_name: str
    document_id: UUID
    page_numbers: list[int] = Field(default_factory=list)
    section_type: str
    relationship_context: str | None = Field(
        default=None,
        description="Relationship path context (e.g., 'Related via: HAS_COVERAGE → MODIFIED_BY')",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "citation_id": "1",
                "document_name": "POL_CA_00_01.pdf",
                "document_id": "123e4567-e89b-12d3-a456-426614174000",
                "page_numbers": [3, 4],
                "section_type": "coverages",
                "relationship_context": "Related via: HAS_COVERAGE → MODIFIED_BY",
            }
        }


class FormattedResponse(BaseModel):
    """Final formatted response with structured sources."""

    answer: str = Field(description="LLM answer with inline citations")
    sources: list[SourceCitation] = Field(description="Structured source citations")

    class Config:
        json_schema_extra = {
            "example": {
                "answer": "Your property deductible is $5,000 per occurrence [1].",
                "sources": [
                    {
                        "citation_id": "1",
                        "document_name": "POL_CA_00_01.pdf",
                        "document_id": "123e4567-e89b-12d3-a456-426614174000",
                        "page_numbers": [3],
                        "section_type": "coverages",
                        "relationship_context": None,
                    }
                ],
            }
        }


# API Models

class GraphRAGRequest(BaseModel):
    """Request model for GraphRAG query endpoint."""

    query: str = Field(min_length=1, description="User's natural language question")
    document_ids: list[UUID] | None = Field(
        default=None, description="Specific documents to query (None = all workflow docs)"
    )
    include_sources: bool = Field(
        default=True, description="Include source citations in response"
    )
    max_context_tokens: int = Field(
        default=8000,
        ge=1000,
        le=32000,
        description="Maximum tokens for context assembly",
    )
    intent_override: Literal["QA", "ANALYSIS", "AUDIT"] | None = Field(
        default=None,
        description="Override automatic intent classification (for testing)",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "query": "What is my property deductible?",
                "document_ids": None,
                "include_sources": True,
                "max_context_tokens": 8000,
                "intent_override": None,
            }
        }


class ResponseMetadata(BaseModel):
    """Metadata about the retrieval process."""

    intent: str = Field(description="Classified or overridden intent")
    traversal_depth: int = Field(description="Graph traversal depth used")
    vector_results_count: int = Field(description="Number of vector search results")
    graph_results_count: int = Field(description="Number of graph traversal results")
    merged_results_count: int = Field(description="Number of merged results")
    full_text_count: int = Field(description="Results with full text in context")
    summary_count: int = Field(description="Results with summaries in context")
    total_context_tokens: int = Field(description="Total tokens in assembled context")
    latency_ms: int = Field(description="Total end-to-end latency")

    # Per-stage latency breakdown
    stage_latencies: dict[str, int] = Field(
        default_factory=dict,
        description="Latency per stage in milliseconds",
    )

    # Graceful degradation flags
    graph_available: bool = Field(
        default=True, description="Whether graph data was available"
    )
    fallback_mode: bool = Field(
        default=False, description="Whether vector-only fallback was used"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "intent": "QA",
                "traversal_depth": 1,
                "vector_results_count": 12,
                "graph_results_count": 8,
                "merged_results_count": 15,
                "full_text_count": 5,
                "summary_count": 10,
                "total_context_tokens": 7500,
                "latency_ms": 1250,
                "stage_latencies": {
                    "query_understanding": 150,
                    "vector_retrieval": 300,
                    "graph_expansion": 400,
                    "context_assembly": 250,
                    "response_generation": 150,
                },
                "graph_available": True,
                "fallback_mode": False,
            }
        }


class GraphRAGResponse(BaseModel):
    """Response model for GraphRAG query endpoint."""

    answer: str = Field(description="LLM-generated answer with inline citations")
    sources: list[SourceCitation] = Field(
        default_factory=list, description="Source citations (empty if include_sources=False)"
    )
    metadata: ResponseMetadata = Field(description="Retrieval process metadata")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Response generation timestamp"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "answer": "Your property deductible is $5,000 per occurrence [1].",
                "sources": [
                    {
                        "citation_id": "1",
                        "document_name": "POL_CA_00_01.pdf",
                        "document_id": "123e4567-e89b-12d3-a456-426614174000",
                        "page_numbers": [3],
                        "section_type": "coverages",
                        "relationship_context": None,
                    }
                ],
                "metadata": {
                    "intent": "QA",
                    "traversal_depth": 1,
                    "vector_results_count": 12,
                    "graph_results_count": 8,
                    "merged_results_count": 15,
                    "full_text_count": 5,
                    "summary_count": 10,
                    "total_context_tokens": 7500,
                    "latency_ms": 1250,
                    "stage_latencies": {},
                    "graph_available": True,
                    "fallback_mode": False,
                },
                "timestamp": "2024-01-15T10:30:00Z",
            }
        }
