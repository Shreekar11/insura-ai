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
    ocr_results: Mapped[list["OCRResult"]] = relationship(
        "OCRResult", back_populates="document", cascade="all, delete-orphan"
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
    image_path: Mapped[str | None] = mapped_column(String, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )

    # Relationships
    document: Mapped["Document"] = relationship("Document", back_populates="pages")
    raw_texts: Mapped[list["DocumentRawText"]] = relationship(
        "DocumentRawText", back_populates="page", cascade="all, delete-orphan"
    )
    ocr_tokens: Mapped[list["OCRToken"]] = relationship(
        "OCRToken", back_populates="page", cascade="all, delete-orphan"
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


class OCRResult(Base):
    """Document-level full OCR result."""

    __tablename__ = "ocr_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    ocr_provider: Mapped[str] = mapped_column(
        String, nullable=False
    )  # mistral_ocr | tesseract | gcv
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    
    # Provenance tracking
    model_version: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="OCR engine version"
    )
    pipeline_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, comment="Links to specific pipeline execution"
    )
    source_stage: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Pipeline stage: ocr"
    )
    
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )

    # Relationships
    document: Mapped["Document"] = relationship("Document", back_populates="ocr_results")


class OCRToken(Base):
    """Token-level OCR structure for layout understanding."""

    __tablename__ = "ocr_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_pages.id", ondelete="CASCADE"),
        nullable=False,
    )
    token: Mapped[str] = mapped_column(String, nullable=False)
    x_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    y_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    x_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    y_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )

    # Relationships
    page: Mapped["DocumentPage"] = relationship("DocumentPage", back_populates="ocr_tokens")


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
    )  # rules | gpt_zero_shot | claude_zero_shot | mistral_zero_shot | chunk_aggregator_v1 | llm_fallback_v1
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
    model_version: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="LLM/normalizer version for provenance"
    )
    quality_score: Mapped[Decimal | None] = mapped_column(
        Numeric, nullable=True, comment="Confidence/quality metric for normalization"
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
    location_number: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Location identifier"
    )
    building_number: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Building identifier"
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Property description"
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
    limit: Mapped[Decimal | None] = mapped_column(
        Numeric, nullable=True, comment="Coverage limit"
    )
    deductible: Mapped[Decimal | None] = mapped_column(
        Numeric, nullable=True, comment="Deductible amount"
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
    claim_number: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Claim identifier"
    )
    insured_name: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Insured party name"
    )
    loss_date: Mapped[datetime | None] = mapped_column(
        Date, nullable=True, comment="Date of loss"
    )
    cause_of_loss: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Loss cause/type"
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
