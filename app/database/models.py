"""SQLAlchemy models for all database tables."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    TIMESTAMP,
    UniqueConstraint,
    Boolean,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from collections.abc import Sequence


class User(Base):
    """User model for Clerk-authenticated users."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    clerk_user_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()", onupdate=datetime.utcnow
    )

    # Relationships
    documents: Mapped[list["Document"]] = relationship(
        "Document", back_populates="user", cascade="all, delete-orphan"
    )


class Document(Base):
    """Document model for uploaded files."""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="uploaded"
    )  # uploaded | ocr_processing | ocr_processed | classified | extracted
    uploaded_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()", nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()", onupdate=datetime.utcnow
    )

    # Relationships
    user: Mapped["User | None"] = relationship("User", back_populates="documents")
    pages: Mapped[list["DocumentPage"]] = relationship(
        "DocumentPage", back_populates="document", cascade="all, delete-orphan"
    )
    classifications: Mapped[list["DocumentClassification"]] = relationship(
        "DocumentClassification",
        back_populates="document",
        cascade="all, delete-orphan",
    )
    extracted_fields: Mapped[list["ExtractedField"]] = relationship(
        "ExtractedField", back_populates="document", cascade="all, delete-orphan"
    )
    workflows: Mapped[list["Workflow"]] = relationship(
        "Workflow", back_populates="document", cascade="all, delete-orphan"
    )
    section_extractions: Mapped[list["SectionExtraction"]] = relationship(
        "SectionExtraction", back_populates="document", cascade="all, delete-orphan"
    )
    entity_mentions: Mapped[list["EntityMention"]] = relationship(
        "EntityMention", back_populates="document", cascade="all, delete-orphan"
    )


class DocumentPage(Base):
    """Page-level metadata for PDFs/images."""

    __tablename__ = "document_pages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_path: Mapped[str | None] = mapped_column(String, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    additional_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )

    # Relationships
    document: Mapped["Document"] = relationship("Document", back_populates="pages")
    raw_texts: Mapped[list["DocumentRawText"]] = relationship(
        "DocumentRawText", back_populates="page", cascade="all, delete-orphan"
    )


class DocumentRawText(Base):
    """OCR text per page."""

    __tablename__ = "document_raw_text"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_pages.id", ondelete="CASCADE"),
        nullable=False,
    )
    text_content: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )

    # Relationships
    page: Mapped["DocumentPage"] = relationship(
        "DocumentPage", back_populates="raw_texts"
    )

class DocumentClassification(Base):
    """Document classification results."""

    __tablename__ = "document_classifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    classified_type: Mapped[str] = mapped_column(
        String, nullable=False
    )  # policy | claim | quote | submission | SOV | proposal | audit | financials | loss_run | endorsement | invoice | correspondence
    confidence: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    classifier_model: Mapped[str | None] = mapped_column(
        String, nullable=True
    )  # rules | gpt_zero_shot | claude_zero_shot | chunk_aggregator_v1 | llm_fallback_v1
    decision_details: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="Aggregation details: scores, method, chunks_used, fallback_used"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )

    # Relationships
    document: Mapped["Document"] = relationship(
        "Document", back_populates="classifications"
    )


class ExtractedField(Base):
    """Extracted fields from documents."""

    __tablename__ = "extracted_fields"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True
    )
    field_name: Mapped[str] = mapped_column(String, nullable=False)
    field_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )

    # Relationships
    document: Mapped["Document | None"] = relationship(
        "Document", back_populates="extracted_fields"
    )


class Workflow(Base):
    """Temporal workflow instances."""

    __tablename__ = "workflows"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True
    )
    workflow_type: Mapped[str] = mapped_column(
        String, nullable=False
    )  # claims_intake | policy_comparison | submission | proposal_generation
    temporal_workflow_id: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="running"
    )  # running | completed | failed
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()", onupdate=datetime.utcnow
    )

    # Relationships
    document: Mapped["Document | None"] = relationship(
        "Document", back_populates="workflows"
    )
    events: Mapped[list["WorkflowRunEvent"]] = relationship(
        "WorkflowRunEvent", back_populates="workflow", cascade="all, delete-orphan"
    )


class WorkflowRunEvent(Base):
    """Audit trail for workflow runs."""

    __tablename__ = "workflow_run_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    event_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )

    # Relationships
    workflow: Mapped["Workflow"] = relationship("Workflow", back_populates="events")


class Submission(Base):
    """Submissions workflow table."""

    __tablename__ = "submissions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True
    )
    submission_type: Mapped[str | None] = mapped_column(
        String, nullable=True
    )  # property | auto | commercial
    agent_name: Mapped[str | None] = mapped_column(String, nullable=True)
    insured_name: Mapped[str | None] = mapped_column(String, nullable=True)
    effective_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    expiration_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )


class PolicyComparison(Base):
    """Policy comparison workflow output."""

    __tablename__ = "policy_comparisons"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True
    )
    comparison_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )


class Claim(Base):
    """Claims intake workflow output."""

    __tablename__ = "claims"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True
    )
    claim_number: Mapped[str | None] = mapped_column(String, nullable=True)
    insured_name: Mapped[str | None] = mapped_column(String, nullable=True)
    loss_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    loss_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )


class Quote(Base):
    """Quote comparison workflow table."""

    __tablename__ = "quotes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True
    )
    carrier_name: Mapped[str | None] = mapped_column(String, nullable=True)
    premium: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )


class Proposal(Base):
    """Proposal generation workflow table."""

    __tablename__ = "proposals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True
    )
    proposal_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )


class FinancialAnalysis(Base):
    """Financial analysis workflow table."""

    __tablename__ = "financial_analysis"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True
    )
    extracted_metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    risk_assessment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )


class PropertySOV(Base):
    """Statement of Values (SOV) table."""

    __tablename__ = "property_sov"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True
    )
    sov_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )


class DocumentChunk(Base):
    """Document chunks for token-limited processing."""

    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    section_name: Mapped[str | None] = mapped_column(String, nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # New columns for vector/graph support
    section_type: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="High-level section: Declarations, Coverages, etc."
    )
    subsection_type: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Fine-grained subsection: Named Insured, Limits, etc."
    )
    stable_chunk_id: Mapped[str | None] = mapped_column(
        String, unique=True, nullable=True, comment="Deterministic ID: doc_{document_id}_p{page}_c{chunk}"
    )
    
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )

    # Relationships
    normalized_chunks: Mapped[list["NormalizedChunk"]] = relationship(
        "NormalizedChunk", back_populates="chunk", cascade="all, delete-orphan"
    )
    entity_mentions: Mapped[list["EntityMention"]] = relationship(
        "EntityMention", foreign_keys="EntityMention.source_document_chunk_id", back_populates="source_chunk"
    )


class NormalizedChunk(Base):
    """Normalized chunks after LLM processing."""

    __tablename__ = "normalized_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=False
    )
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalization_method: Mapped[str] = mapped_column(
        String, nullable=False, default="llm"
    )  # llm | hybrid | rule_based
    processing_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extracted_fields: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    
    # New columns for vector/graph support
    entities: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Structured entity mentions extracted from chunk"
    )
    relationships: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Structured relationships between entities"
    )
    
    # Provenance tracking
    content_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True, comment="SHA256 hash of normalized_text for change detection"
    )
    model_version: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="LLM/normalizer version for provenance"
    )
    prompt_version: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Prompt template version used"
    )
    pipeline_run_id: Mapped[str | None] = mapped_column(
        String, nullable=True, index=True, comment="Pipeline execution identifier"
    )
    source_stage: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Pipeline stage that created this (normalization, extraction, etc.)"
    )
    quality_score: Mapped[Decimal | None] = mapped_column(
        Numeric, nullable=True, comment="Confidence/quality metric for normalization"
    )
    extracted_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True, comment="When extraction was performed"
    )
    
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )

    # Relationships
    chunk: Mapped["DocumentChunk"] = relationship(
        "DocumentChunk", back_populates="normalized_chunks"
    )


class ChunkClassificationSignal(Base):
    """Classification signals extracted from document chunks."""

    __tablename__ = "chunk_classification_signals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=False
    )
    signals: Mapped[dict] = mapped_column(
        JSON, nullable=False, comment="Per-class confidence scores: {policy: 0.12, claim: 0.78, ...}"
    )
    keywords: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="Extracted keywords/phrases indicating document type"
    )
    entities: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="Extracted entities: policy_number, claim_number, dates, amounts"
    )
    model_name: Mapped[str] = mapped_column(String, nullable=False)
    model_confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4), nullable=True, comment="LLM confidence in signal extraction"
    )
    
    # Provenance tracking
    model_version: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Classifier model version"
    )
    pipeline_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, comment="Links to specific pipeline execution"
    )
    source_stage: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Pipeline stage: classification"
    )
    
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )

    # Relationships
    chunk: Mapped["DocumentChunk"] = relationship("DocumentChunk")


# ============================================================================
# Vector Indexing & Knowledge Graph Models
# ============================================================================


class ChunkEmbedding(Base):
    """Embeddings for normalized chunks with versioning support."""

    __tablename__ = "chunk_embeddings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("normalized_chunks.id", ondelete="CASCADE"), nullable=False
    )
    embedding_model: Mapped[str] = mapped_column(
        String, nullable=False, comment="Model name: text-embedding-3-large, etc."
    )
    embedding_version: Mapped[str] = mapped_column(
        String, nullable=False, comment="Model version for tracking updates"
    )
    embedding_dimension: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Vector dimension: 1536, 3072, etc."
    )
    embedding: Mapped[dict] = mapped_column(
        JSONB, nullable=False, comment="JSONB array of floats representing the vector"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )

    # Relationships
    chunk: Mapped["NormalizedChunk"] = relationship("NormalizedChunk")


class CanonicalEntity(Base):
    """Unique, deduplicated entities across all documents."""

    __tablename__ = "canonical_entities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    entity_type: Mapped[str] = mapped_column(
        String, nullable=False, comment="POLICY, CLAIM, INSURED, ADDRESS, CARRIER, etc."
    )
    canonical_key: Mapped[str] = mapped_column(
        String, nullable=False, comment="Unique identifier: policy number, claim number, etc."
    )
    attributes: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Entity properties: name, dates, amounts, etc."
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()", onupdate=datetime.utcnow
    )

    # Relationships
    chunk_entity_links: Mapped[list["ChunkEntityLink"]] = relationship(
        "ChunkEntityLink", back_populates="canonical_entity"
    )
    document_entity_links: Mapped[list["DocumentEntityLink"]] = relationship(
        "DocumentEntityLink", back_populates="canonical_entity"
    )
    source_relationships: Mapped[list["EntityRelationship"]] = relationship(
        "EntityRelationship", foreign_keys="EntityRelationship.source_entity_id", back_populates="source_entity"
    )
    target_relationships: Mapped[list["EntityRelationship"]] = relationship(
        "EntityRelationship", foreign_keys="EntityRelationship.target_entity_id", back_populates="target_entity"
    )
    evidence_records: Mapped[list["EntityEvidence"]] = relationship(
        "EntityEvidence", back_populates="canonical_entity", cascade="all, delete-orphan"
    )
    entity_attributes: Mapped[list["EntityAttribute"]] = relationship(
        "EntityAttribute", back_populates="canonical_entity", cascade="all, delete-orphan"
    )
    # Typed canonical entity relationships (1:1)
    insured_entity: Mapped["InsuredEntity | None"] = relationship(
        "InsuredEntity", foreign_keys="InsuredEntity.id", uselist=False
    )
    carrier_entity: Mapped["CarrierEntity | None"] = relationship(
        "CarrierEntity", foreign_keys="CarrierEntity.id", uselist=False
    )
    policy_entity: Mapped["PolicyEntity | None"] = relationship(
        "PolicyEntity", foreign_keys="PolicyEntity.id", uselist=False
    )
    claim_entity: Mapped["ClaimEntity | None"] = relationship(
        "ClaimEntity", foreign_keys="ClaimEntity.id", uselist=False
    )

    # Unique constraint
    __table_args__ = (
        UniqueConstraint("entity_type", "canonical_key", name="uq_entity_type_canonical_key"),
        {"comment": "Canonical entities with unique (entity_type, canonical_key)"},
    )


class ChunkEntityMention(Base):
    """Fine-grained entity mentions detected in chunks."""

    __tablename__ = "chunk_entity_mentions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("normalized_chunks.id", ondelete="CASCADE"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(
        String, nullable=False, comment="Type of entity mentioned"
    )
    raw_value: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Original text as it appears in chunk"
    )
    normalized_value: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Cleaned/standardized value"
    )
    confidence: Mapped[Decimal | None] = mapped_column(
        Numeric, nullable=True, comment="Detection confidence (0.0-1.0)"
    )
    span_start: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Character offset start"
    )
    span_end: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Character offset end"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )

    # Relationships
    chunk: Mapped["NormalizedChunk"] = relationship("NormalizedChunk")


class EntityRelationship(Base):
    """Structured relationships extracted by LLM/normalizer."""

    __tablename__ = "entity_relationships"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_entities.id"), nullable=True
    )
    target_entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_entities.id"), nullable=True
    )
    relationship_type: Mapped[str] = mapped_column(
        String, nullable=False, comment="HAS_CLAIM, INSURED_BY, HAS_COVERAGE, LOCATED_AT, etc."
    )
    attributes: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Relationship metadata"
    )
    confidence: Mapped[Decimal | None] = mapped_column(
        Numeric, nullable=True, comment="Extraction confidence"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )

    # Relationships
    source_entity: Mapped["CanonicalEntity | None"] = relationship(
        "CanonicalEntity", foreign_keys=[source_entity_id]
    )
    target_entity: Mapped["CanonicalEntity | None"] = relationship(
        "CanonicalEntity", foreign_keys=[target_entity_id]
    )


class ChunkEntityLink(Base):
    """Maps chunk-level mentions to canonical entities after resolution."""

    __tablename__ = "chunk_entity_links"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("normalized_chunks.id", ondelete="CASCADE"), nullable=False
    )
    canonical_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_entities.id", ondelete="CASCADE"), nullable=False
    )
    confidence: Mapped[Decimal | None] = mapped_column(
        Numeric, nullable=True, comment="Linking confidence"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )

    # Relationships
    chunk: Mapped["NormalizedChunk"] = relationship("NormalizedChunk")
    canonical_entity: Mapped["CanonicalEntity"] = relationship("CanonicalEntity")


class DocumentEntityLink(Base):
    """Links canonical entities to entire documents."""

    __tablename__ = "document_entity_links"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    canonical_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_entities.id", ondelete="CASCADE"), nullable=False
    )
    confidence: Mapped[Decimal | None] = mapped_column(
        Numeric, nullable=True, comment="Linking confidence"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )

    # Relationships
    document: Mapped["Document"] = relationship("Document")
    canonical_entity: Mapped["CanonicalEntity"] = relationship("CanonicalEntity")


class GraphSyncState(Base):
    """Tracks synchronization of SQL entities with Neo4j graph database."""

    __tablename__ = "graph_sync_state"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_table: Mapped[str] = mapped_column(
        String, nullable=False, comment="Table name: canonical_entities, entity_relationships, etc."
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, comment="Record ID in source table"
    )
    neo4j_node_id: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Neo4j internal node/relationship ID"
    )
    last_sync_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True, comment="Last successful sync time"
    )
    sync_status: Mapped[str] = mapped_column(
        String, nullable=False, default="pending", comment="pending, synced, failed"
    )
    sync_error: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Error message if sync failed"
    )


class EmbeddingSyncState(Base):
    """Tracks embedding sync status with Neo4j vector index."""

    __tablename__ = "embedding_sync_state"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("normalized_chunks.id", ondelete="CASCADE"), nullable=False
    )
    last_embedding_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True, comment="When embedding was last generated"
    )
    embedding_model: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Model used"
    )
    embedding_version: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Version used"
    )
    sync_status: Mapped[str] = mapped_column(
        String, nullable=False, default="pending", comment="pending, synced, failed"
    )
    sync_error: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Error message if sync failed"
    )

    # Relationships
    chunk: Mapped["NormalizedChunk"] = relationship("NormalizedChunk")


class SOVItem(Base):
    """Structured extraction of Statement of Values items."""

    __tablename__ = "sov_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True
    )
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_chunks.id"), nullable=True
    )
    location_number: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Location identifier"
    )
    building_number: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Building identifier"
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Property description"
    )
    address: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Property address"
    )
    construction_type: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Construction class"
    )
    occupancy: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Occupancy type"
    )
    year_built: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Year of construction"
    )
    square_footage: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Building size"
    )
    building_limit: Mapped[Decimal | None] = mapped_column(
        Numeric, nullable=True, comment="Building coverage limit"
    )
    contents_limit: Mapped[Decimal | None] = mapped_column(
        Numeric, nullable=True, comment="Contents coverage limit"
    )
    bi_limit: Mapped[Decimal | None] = mapped_column(
        Numeric, nullable=True, comment="Business interruption limit"
    )
    total_insured_value: Mapped[Decimal | None] = mapped_column(
        Numeric, nullable=True, comment="Total insured value (TIV)"
    )
    additional_data: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Additional fields"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )

    # Relationships
    document: Mapped["Document | None"] = relationship("Document")


class LossRunClaim(Base):
    """Structured extraction of loss run claim items."""

    __tablename__ = "loss_run_claims"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True
    )
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_chunks.id"), nullable=True
    )
    claim_number: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Claim identifier"
    )
    policy_number: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Associated policy number"
    )
    insured_name: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Insured party name"
    )
    loss_date: Mapped[datetime | None] = mapped_column(
        Date, nullable=True, comment="Date of loss"
    )
    report_date: Mapped[datetime | None] = mapped_column(
        Date, nullable=True, comment="Date claim was reported"
    )
    cause_of_loss: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Loss cause/type"
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Claim description"
    )
    incurred_amount: Mapped[Decimal | None] = mapped_column(
        Numeric, nullable=True, comment="Total incurred"
    )
    paid_amount: Mapped[Decimal | None] = mapped_column(
        Numeric, nullable=True, comment="Amount paid"
    )
    reserve_amount: Mapped[Decimal | None] = mapped_column(
        Numeric, nullable=True, comment="Reserve amount"
    )
    status: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Claim status"
    )
    additional_data: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Additional fields"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )

    # Relationships
    document: Mapped["Document | None"] = relationship("Document")


class PolicyItem(Base):
    """Structured extraction of policy information."""

    __tablename__ = "policy_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True
    )
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_chunks.id"), nullable=True
    )
    policy_number: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Policy identification number"
    )
    policy_type: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Type of policy (Property, Auto, GL, etc.)"
    )
    insured_name: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Name of insured party"
    )
    effective_date: Mapped[datetime | None] = mapped_column(
        Date, nullable=True, comment="Policy effective date"
    )
    expiration_date: Mapped[datetime | None] = mapped_column(
        Date, nullable=True, comment="Policy expiration date"
    )
    premium_amount: Mapped[Decimal | None] = mapped_column(
        Numeric, nullable=True, comment="Total premium"
    )
    coverage_limits: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Coverage limits by type"
    )
    deductibles: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Deductibles by coverage type"
    )
    carrier_name: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Insurance carrier"
    )
    agent_name: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Agent/broker name"
    )
    additional_data: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Additional fields"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )

    # Relationships
    document: Mapped["Document | None"] = relationship("Document")


class EndorsementItem(Base):
    """Structured extraction of policy endorsement/amendment information."""

    __tablename__ = "endorsement_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True
    )
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_chunks.id"), nullable=True
    )
    endorsement_number: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Endorsement identifier"
    )
    policy_number: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Associated policy number"
    )
    effective_date: Mapped[datetime | None] = mapped_column(
        Date, nullable=True, comment="Endorsement effective date"
    )
    change_type: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Type of change (Addition, Deletion, Modification)"
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Description of change"
    )
    premium_change: Mapped[Decimal | None] = mapped_column(
        Numeric, nullable=True, comment="Premium impact (positive or negative)"
    )
    coverage_changes: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Coverage modifications"
    )
    additional_data: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Additional fields"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )

    # Relationships
    document: Mapped["Document | None"] = relationship("Document")


class InvoiceItem(Base):
    """Structured extraction of invoice and payment information."""

    __tablename__ = "invoice_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True
    )
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_chunks.id"), nullable=True
    )
    invoice_number: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Invoice identifier"
    )
    policy_number: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Associated policy number"
    )
    invoice_date: Mapped[datetime | None] = mapped_column(
        Date, nullable=True, comment="Invoice date"
    )
    due_date: Mapped[datetime | None] = mapped_column(
        Date, nullable=True, comment="Payment due date"
    )
    total_amount: Mapped[Decimal | None] = mapped_column(
        Numeric, nullable=True, comment="Total invoice amount"
    )
    amount_paid: Mapped[Decimal | None] = mapped_column(
        Numeric, nullable=True, comment="Amount paid to date"
    )
    balance_due: Mapped[Decimal | None] = mapped_column(
        Numeric, nullable=True, comment="Remaining balance"
    )
    payment_status: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Status (Paid, Pending, Overdue)"
    )
    payment_method: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Payment method if paid"
    )
    additional_data: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Additional fields"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )

    # Relationships
    document: Mapped["Document | None"] = relationship("Document")


class ConditionItem(Base):
    """Structured extraction of policy conditions."""

    __tablename__ = "condition_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True
    )
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_chunks.id"), nullable=True
    )
    condition_type: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Type of condition"
    )
    title: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Condition title"
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Full description"
    )
    applies_to: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="What it applies to"
    )
    requirements: Mapped[list | None] = mapped_column(
        JSONB, nullable=True, comment="List of requirements"
    )
    consequences: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Consequences of non-compliance"
    )
    reference: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Section reference"
    )
    additional_data: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Additional fields"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )

    # Relationships
    document: Mapped["Document | None"] = relationship("Document")


class CoverageItem(Base):
    """Structured extraction of coverage information."""

    __tablename__ = "coverage_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True
    )
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_chunks.id"), nullable=True
    )
    coverage_name: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Name of coverage"
    )
    coverage_type: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Type/category"
    )
    limit_amount: Mapped[Decimal | None] = mapped_column(
        Numeric, nullable=True, comment="Coverage limit"
    )
    deductible_amount: Mapped[Decimal | None] = mapped_column(
        Numeric, nullable=True, comment="Deductible amount"
    )
    premium_amount: Mapped[Decimal | None] = mapped_column(
        Numeric, nullable=True, comment="Premium for this coverage"
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Coverage description"
    )
    sub_limits: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Sub-limits"
    )
    exclusions: Mapped[list | None] = mapped_column(
        JSONB, nullable=True, comment="Specific exclusions"
    )
    conditions: Mapped[list | None] = mapped_column(
        JSONB, nullable=True, comment="Specific conditions"
    )
    per_occurrence: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True, comment="Is per occurrence"
    )
    aggregate: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True, comment="Is aggregate limit"
    )
    additional_data: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Additional fields"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )

    # Relationships
    document: Mapped["Document | None"] = relationship("Document")


class ExclusionItem(Base):
    """Structured extraction of policy exclusions."""

    __tablename__ = "exclusion_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True
    )
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_chunks.id"), nullable=True
    )
    exclusion_type: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Type of exclusion"
    )
    title: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Exclusion title"
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Full description"
    )
    applies_to: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="What it applies to"
    )
    scope: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Scope (Total/Partial)"
    )
    exceptions: Mapped[list | None] = mapped_column(
        JSONB, nullable=True, comment="Exceptions to exclusion"
    )
    rationale: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Reason for exclusion"
    )
    reference: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Section reference"
    )
    additional_data: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Additional fields"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )

    # Relationships
    document: Mapped["Document | None"] = relationship("Document")


class KYCItem(Base):
    """Structured extraction of KYC information."""

    __tablename__ = "kyc_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True
    )
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_chunks.id"), nullable=True
    )
    customer_name: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Customer/Entity name"
    )
    customer_type: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Type (Individual/Entity)"
    )
    date_of_birth: Mapped[datetime | None] = mapped_column(
        Date, nullable=True, comment="DOB for individuals"
    )
    incorporation_date: Mapped[datetime | None] = mapped_column(
        Date, nullable=True, comment="Incorporation date for entities"
    )
    tax_id: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Tax ID / SSN / EIN"
    )
    business_type: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Business type"
    )
    industry: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Industry sector"
    )
    address: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Full address"
    )
    city: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="City"
    )
    state: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="State"
    )
    zip_code: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="ZIP code"
    )
    country: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Country"
    )
    phone: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Phone number"
    )
    email: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Email address"
    )
    website: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Website URL"
    )
    identification_type: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="ID type"
    )
    identification_number: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="ID number"
    )
    identification_issuer: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Issuing authority"
    )
    identification_expiry: Mapped[datetime | None] = mapped_column(
        Date, nullable=True, comment="ID expiry date"
    )
    authorized_signers: Mapped[list | None] = mapped_column(
        JSONB, nullable=True, comment="List of authorized signers"
    )
    ownership_structure: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Ownership details"
    )
    annual_revenue: Mapped[Decimal | None] = mapped_column(
        Numeric, nullable=True, comment="Annual revenue"
    )
    employee_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Number of employees"
    )
    additional_data: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Additional fields"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )

    # Relationships
    document: Mapped["Document | None"] = relationship("Document")


class ClaimItem(Base):
    """Structured extraction of claims information from documents."""

    __tablename__ = "claim_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True
    )
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_chunks.id"), nullable=True
    )
    claim_number: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Claim identifier"
    )
    policy_number: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Associated policy number"
    )
    claimant_name: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Name of claimant"
    )
    loss_date: Mapped[datetime | None] = mapped_column(
        Date, nullable=True, comment="Date of loss"
    )
    report_date: Mapped[datetime | None] = mapped_column(
        Date, nullable=True, comment="Date claim was reported"
    )
    claim_type: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Type of claim"
    )
    loss_description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Description of loss"
    )
    loss_location: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Location of loss"
    )
    claim_amount: Mapped[Decimal | None] = mapped_column(
        Numeric, nullable=True, comment="Claimed amount"
    )
    paid_amount: Mapped[Decimal | None] = mapped_column(
        Numeric, nullable=True, comment="Amount paid"
    )
    reserve_amount: Mapped[Decimal | None] = mapped_column(
        Numeric, nullable=True, comment="Reserve amount"
    )
    claim_status: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Status (Open, Closed, etc.)"
    )
    adjuster_name: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Name of adjuster"
    )
    denial_reason: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Reason for denial"
    )
    additional_data: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Additional fields"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )

    # Relationships
    document: Mapped["Document | None"] = relationship("Document")


# ============================================================================
# Page-Level Analysis Models (v2 Architecture)
# ============================================================================


class PageAnalysis(Base):
    """Lightweight signals extracted from PDF pages for classification."""

    __tablename__ = "page_analysis"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    page_number: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="1-indexed page number"
    )
    top_lines: Mapped[list] = mapped_column(
        JSONB, nullable=False, comment="First 5-10 lines of text from page"
    )
    text_density: Mapped[Decimal] = mapped_column(
        Numeric(5, 3), nullable=False, comment="Text density ratio (0.0 to 1.0)"
    )
    has_tables: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="Whether page contains tables"
    )
    max_font_size: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 2), nullable=True, comment="Largest font size (indicates headers)"
    )
    page_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="Hash for duplicate detection"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )

    # Unique constraint: one analysis per page per document
    __table_args__ = (
        UniqueConstraint("document_id", "page_number", name="uq_page_analysis_doc_page"),
        {"comment": "Lightweight page signals for classification"},
    )


class PageClassificationResult(Base):
    """Classification results for document pages."""

    __tablename__ = "page_classifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    page_number: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="1-indexed page number"
    )
    page_type: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="declarations | coverages | conditions | exclusions | endorsement | sov | loss_run | invoice | boilerplate | duplicate | unknown"
    )
    confidence: Mapped[Decimal] = mapped_column(
        Numeric(5, 3), nullable=False, comment="Classification confidence (0.0 to 1.0)"
    )
    should_process: Mapped[bool] = mapped_column(
        Boolean, nullable=False, comment="Whether to perform full OCR on this page"
    )
    duplicate_of: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Page number this is a duplicate of"
    )
    reasoning: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Human-readable classification reasoning"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )

    # Unique constraint: one classification per page per document
    __table_args__ = (
        UniqueConstraint("document_id", "page_number", name="uq_page_classification_doc_page"),
        {"comment": "Page classification results"},
    )


class PageManifestRecord(Base):
    """Page manifest summary for documents (determines which pages to process)."""

    __tablename__ = "page_manifests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    total_pages: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Total number of pages in document"
    )
    pages_to_process: Mapped[list] = mapped_column(
        JSONB, nullable=False, comment="Array of page numbers to process"
    )
    pages_skipped: Mapped[list] = mapped_column(
        JSONB, nullable=False, comment="Array of page numbers to skip"
    )
    processing_ratio: Mapped[Decimal] = mapped_column(
        Numeric(5, 3), nullable=False, comment="Percentage of pages to process (0.0 to 1.0)"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )

    __table_args__ = (
        {"comment": "Page processing manifest for cost optimization"},
    )


# ============================================================================
# Table Extraction Models (TableJSON Storage)
# ============================================================================


class DocumentTable(Base):
    """First-class table representation with full structural information.
    
    Stores TableJSON data for any detected table, preserving:
    - Cell-level structure (rows, cols, spans, bboxes)
    - Extraction provenance and confidence metrics
    - Classification and canonicalization results
    """

    __tablename__ = "document_tables"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    page_number: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="1-indexed page number"
    )
    table_index: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="0-indexed table position on page"
    )
    stable_table_id: Mapped[str] = mapped_column(
        String, unique=True, nullable=False, comment="Deterministic ID: tbl_{doc_id}_p{page}_t{index}"
    )
    
    # Table structure as JSON
    table_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, comment="Full TableJSON with cells, headers, spans, bboxes"
    )
    
    # Bounding box for table region
    table_bbox: Mapped[list | None] = mapped_column(
        JSONB, nullable=True, comment="[x1, y1, x2, y2] coordinates on page"
    )
    
    # Structure metrics
    num_rows: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Total row count"
    )
    num_cols: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Total column count"
    )
    header_rows: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, comment="Indices of header rows"
    )
    canonical_headers: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, comment="Reconstructed header strings"
    )
    
    # Classification
    table_type: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="property_sov, loss_run, premium_schedule, etc."
    )
    classification_confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4), nullable=True, comment="Classification confidence (0.0-1.0)"
    )
    classification_reasoning: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Human-readable classification reasoning"
    )
    
    # Extraction provenance
    extraction_source: Mapped[str] = mapped_column(
        String, nullable=False, default="docling_structural",
        comment="docling_structural, docling_markdown, camelot, tabula, etc."
    )
    extractor_version: Mapped[str] = mapped_column(
        String, nullable=False, default="1.0.0", comment="Version of extractor"
    )
    
    # Confidence metrics
    confidence_overall: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4), nullable=True, comment="Overall extraction confidence"
    )
    confidence_metrics: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Detailed confidence metrics"
    )
    
    # Raw data for debugging
    raw_markdown: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Original markdown representation"
    )
    notes: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Footer/footnote text"
    )
    
    # Additional metadata
    additional_metadata: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Additional extraction metadata"
    )
    
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()", onupdate=datetime.utcnow
    )

    # Relationships
    document: Mapped["Document"] = relationship("Document")

    __table_args__ = (
        UniqueConstraint("document_id", "page_number", "table_index", name="uq_document_table_position"),
        {"comment": "First-class table storage with full structural information"},
    )


# ============================================================================
# Section + Entity Persistence Models (Layered Architecture)
# ============================================================================


class SectionExtraction(Base):
    """Raw section-level extraction output store (Layer 1).
    
    Stores raw LLM extraction output per section without forcing rigid schemas.
    This is the extraction source of truth for section-level data.
    """

    __tablename__ = "section_extractions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    section_type: Mapped[str] = mapped_column(
        String, nullable=False, comment="Section type: Declarations, Coverages, SOV, LossRun, etc."
    )
    page_range: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Page range: {start: int, end: int}"
    )
    extracted_fields: Mapped[dict] = mapped_column(
        JSONB, nullable=False, comment="Raw extracted fields from LLM (JSONB)"
    )
    confidence: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Confidence metrics per field"
    )
    source_chunks: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Source chunk references: {chunk_ids: [], stable_chunk_ids: []}"
    )
    pipeline_run_id: Mapped[str | None] = mapped_column(
        String, nullable=True, index=True, comment="Pipeline execution identifier"
    )
    model_version: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="LLM model version for provenance"
    )
    prompt_version: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Prompt template version used"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )

    # Relationships
    document: Mapped["Document"] = relationship("Document")
    entity_mentions: Mapped[list["EntityMention"]] = relationship(
        "EntityMention", back_populates="section_extraction", cascade="all, delete-orphan"
    )

    __table_args__ = (
        {"comment": "Raw section-level extraction output store"},
    )


class EntityMention(Base):
    """Document-scoped entity mentions (Layer 1 for entities).
    
    Stores raw entity mentions extracted from documents/sections.
    Multiple mentions per entity are allowed (ambiguity preserved).
    """

    __tablename__ = "entity_mentions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    section_extraction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("section_extractions.id", ondelete="SET NULL"), nullable=True
    )
    entity_type: Mapped[str] = mapped_column(
        String, nullable=False, comment="Entity type: INSURED, CARRIER, POLICY, CLAIM, etc."
    )
    mention_text: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Original text as it appears in document"
    )
    extracted_fields: Mapped[dict] = mapped_column(
        JSONB, nullable=False, comment="Raw mention payload from LLM extraction"
    )
    confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4), nullable=True, comment="Overall confidence (0.0-1.0)"
    )
    confidence_details: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Detailed confidence metrics"
    )
    source_document_chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_chunks.id", ondelete="SET NULL"), nullable=True
    )
    source_stable_chunk_id: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Deterministic chunk ID for provenance"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )

    # Relationships
    document: Mapped["Document"] = relationship("Document")
    section_extraction: Mapped["SectionExtraction | None"] = relationship(
        "SectionExtraction", back_populates="entity_mentions"
    )
    source_chunk: Mapped["DocumentChunk | None"] = relationship("DocumentChunk")
    evidence_records: Mapped[list["EntityEvidence"]] = relationship(
        "EntityEvidence", back_populates="entity_mention", cascade="all, delete-orphan"
    )
    entity_attributes: Mapped[list["EntityAttribute"]] = relationship(
        "EntityAttribute", back_populates="source_entity_mention", cascade="all, delete-orphan"
    )

    __table_args__ = (
        {"comment": "Document-scoped entity mentions with ambiguity allowed"},
    )


class EntityEvidence(Base):
    """Entity evidence mapping (Layer 3).
    
    Maps canonical entities to their source mentions, providing explainability
    and audit trail for why canonical entities exist.
    """

    __tablename__ = "entity_evidence"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    canonical_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_entities.id", ondelete="CASCADE"), nullable=False
    )
    entity_mention_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entity_mentions.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4), nullable=True, comment="Evidence confidence (0.0-1.0)"
    )
    evidence_type: Mapped[str] = mapped_column(
        String, nullable=False, default="extracted",
        comment="Evidence type: extracted, inferred, human_verified"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )

    # Relationships
    canonical_entity: Mapped["CanonicalEntity"] = relationship("CanonicalEntity")
    entity_mention: Mapped["EntityMention"] = relationship(
        "EntityMention", back_populates="evidence_records"
    )
    document: Mapped["Document"] = relationship("Document")

    __table_args__ = (
        {"comment": "Evidence mapping for canonical entities (explainability/audit)"},
    )


class EntityAttribute(Base):
    """Entity attributes (Layer 4, optional).
    
    Attribute-level provenance for canonical entities, enabling temporal
    tracking and conflicting value management.
    """

    __tablename__ = "entity_attributes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    canonical_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_entities.id", ondelete="CASCADE"), nullable=False
    )
    attribute_name: Mapped[str] = mapped_column(
        String, nullable=False, comment="Attribute name"
    )
    attribute_value: Mapped[str | dict] = mapped_column(
        JSONB, nullable=False, comment="Attribute value (text or JSONB)"
    )
    confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4), nullable=True, comment="Attribute confidence (0.0-1.0)"
    )
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    source_entity_mention_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entity_mentions.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )

    # Relationships
    canonical_entity: Mapped["CanonicalEntity"] = relationship("CanonicalEntity")
    source_document: Mapped["Document | None"] = relationship("Document")
    source_entity_mention: Mapped["EntityMention | None"] = relationship(
        "EntityMention", back_populates="entity_attributes"
    )

    __table_args__ = (
        {"comment": "Attribute-level provenance for canonical entities"},
    )


# Typed Canonical Entity Tables (Layer 2 - Structured)
# These are 1:1 with canonical_entities via id as FK


class InsuredEntity(Base):
    """Typed canonical entity table for insured parties."""

    __tablename__ = "insured_entities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("canonical_entities.id", ondelete="CASCADE"),
        primary_key=True,
        comment="1:1 FK to canonical_entities.id"
    )
    canonical_name: Mapped[str] = mapped_column(
        String, nullable=False, comment="Canonical insured name"
    )
    normalized_name: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Normalized name for matching"
    )
    primary_address: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Primary address"
    )
    confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4), nullable=True, comment="Entity confidence"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()", onupdate=datetime.utcnow
    )

    # Relationships
    canonical_entity: Mapped["CanonicalEntity"] = relationship(
        "CanonicalEntity", foreign_keys=[id], overlaps="insured_entity"
    )

    __table_args__ = (
        {"comment": "Typed canonical entity table for insured parties"},
    )


class CarrierEntity(Base):
    """Typed canonical entity table for insurance carriers."""

    __tablename__ = "carrier_entities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("canonical_entities.id", ondelete="CASCADE"),
        primary_key=True,
        comment="1:1 FK to canonical_entities.id"
    )
    canonical_name: Mapped[str] = mapped_column(
        String, nullable=False, comment="Canonical carrier name"
    )
    normalized_name: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Normalized name for matching"
    )
    naic: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="NAIC code"
    )
    confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4), nullable=True, comment="Entity confidence"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()", onupdate=datetime.utcnow
    )

    # Relationships
    canonical_entity: Mapped["CanonicalEntity"] = relationship(
        "CanonicalEntity", foreign_keys=[id], overlaps="carrier_entity"
    )

    __table_args__ = (
        {"comment": "Typed canonical entity table for insurance carriers"},
    )


class PolicyEntity(Base):
    """Typed canonical entity table for policies."""

    __tablename__ = "policy_entities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("canonical_entities.id", ondelete="CASCADE"),
        primary_key=True,
        comment="1:1 FK to canonical_entities.id"
    )
    policy_number: Mapped[str] = mapped_column(
        String, nullable=False, comment="Policy number"
    )
    effective_date: Mapped[datetime | None] = mapped_column(
        Date, nullable=True, comment="Policy effective date"
    )
    expiration_date: Mapped[datetime | None] = mapped_column(
        Date, nullable=True, comment="Policy expiration date"
    )
    confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4), nullable=True, comment="Entity confidence"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()", onupdate=datetime.utcnow
    )

    # Relationships
    canonical_entity: Mapped["CanonicalEntity"] = relationship(
        "CanonicalEntity", foreign_keys=[id], overlaps="policy_entity"
    )

    __table_args__ = (
        {"comment": "Typed canonical entity table for policies"},
    )


class ClaimEntity(Base):
    """Typed canonical entity table for claims."""

    __tablename__ = "claim_entities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("canonical_entities.id", ondelete="CASCADE"),
        primary_key=True,
        comment="1:1 FK to canonical_entities.id"
    )
    claim_number: Mapped[str] = mapped_column(
        String, nullable=False, comment="Claim number"
    )
    loss_date: Mapped[datetime | None] = mapped_column(
        Date, nullable=True, comment="Loss date"
    )
    confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4), nullable=True, comment="Entity confidence"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()", onupdate=datetime.utcnow
    )

    # Relationships
    canonical_entity: Mapped["CanonicalEntity"] = relationship(
        "CanonicalEntity", foreign_keys=[id], overlaps="claim_entity"
    )

    __table_args__ = (
        {"comment": "Typed canonical entity table for claims"},
    )
