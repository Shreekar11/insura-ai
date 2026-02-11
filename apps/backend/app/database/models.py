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
from pgvector.sqlalchemy import Vector

from app.core.database import Base

if TYPE_CHECKING:
    from collections.abc import Sequence


class User(Base):
    """User model for Supabase-authenticated users."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    supabase_user_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
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
    document_name: Mapped[str | None] = mapped_column(String, nullable=True)
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
    classifications: Mapped[list["PageClassificationResult"]] = relationship(
        "PageClassificationResult", back_populates="document", cascade="all, delete-orphan"
    )
    workflow_documents: Mapped[list["WorkflowDocument"]] = relationship(
        "WorkflowDocument", back_populates="document", cascade="all, delete-orphan"
    )
    section_extractions: Mapped[list["SectionExtraction"]] = relationship(
        "SectionExtraction", back_populates="document", cascade="all, delete-orphan"
    )
    entity_mentions: Mapped[list["EntityMention"]] = relationship(
        "EntityMention", back_populates="document", cascade="all, delete-orphan"
    )
    stage_runs: Mapped[list["WorkflowDocumentStageRun"]] = relationship(
        "WorkflowDocumentStageRun", back_populates="document", cascade="all, delete-orphan"
    )
    vector_embeddings: Mapped[list["VectorEmbedding"]] = relationship(
        "VectorEmbedding", back_populates="document", cascade="all, delete-orphan"
    )
    citations: Mapped[list["Citation"]] = relationship(
        "Citation", back_populates="document", cascade="all, delete-orphan"
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

    # Page dimensions for citation coordinate transformation
    width_points: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 4), nullable=True,
        comment="Page width in PDF points (1 point = 1/72 inch)"
    )
    height_points: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 4), nullable=True,
        comment="Page height in PDF points"
    )
    rotation: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=0,
        comment="Page rotation in degrees (0, 90, 180, 270)"
    )

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )

    # Relationships
    document: Mapped["Document"] = relationship("Document", back_populates="pages")


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
    section_type: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="High-level section: Declarations, Coverages, etc."
    )
    subsection_type: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Fine-grained subsection: Named Insured, Limits, etc."
    )
    effective_section_type: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Effective section for extraction routing (may differ from section_type for endorsements)"
    )
    semantic_role: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Semantic role: coverage_modifier, exclusion_modifier, both, administrative_only, etc."
    )
    stable_chunk_id: Mapped[str | None] = mapped_column(
        String, unique=True, nullable=True, comment="Deterministic ID: doc_{document_id}_p{page}_c{chunk}"
    )
    
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )

    # Relationships
    entity_mentions: Mapped[list["EntityMention"]] = relationship(
        "EntityMention", foreign_keys="EntityMention.source_document_chunk_id", back_populates="source_chunk"
    )


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

    # Relationships
    document: Mapped["Document"] = relationship("Document")

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
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
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
    workflow: Mapped["Workflow"] = relationship("Workflow")

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
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=True
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

    # Unique constraint
    __table_args__ = (
        UniqueConstraint("entity_type", "canonical_key", name="uq_entity_type_canonical_key"),
        {"comment": "Canonical entities with unique (entity_type, canonical_key)"},
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


class StepSectionOutput(Base):
    """Step-scoped section output.
    
    Stores normalized section-level results for a specific workflow step.
    This creates a clean boundary after raw extraction.
    """

    __tablename__ = "step_section_outputs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )
    section_type: Mapped[str] = mapped_column(
        String, nullable=False, comment="Section type: Declarations, Coverages, etc."
    )
    display_payload: Mapped[dict] = mapped_column(
        JSONB, nullable=False, comment="Normalized display payload"
    )
    confidence: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Confidence metrics"
    )
    page_range: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Page range: {start: int, end: int}"
    )
    source_section_extraction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("section_extractions.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )

    # Relationships
    document: Mapped["Document"] = relationship("Document")
    workflow: Mapped["Workflow"] = relationship("Workflow")
    section_extraction: Mapped["SectionExtraction | None"] = relationship("SectionExtraction")

    __table_args__ = (
        {"comment": "Step-scoped section level outputs"},
    )


class StepEntityOutput(Base):
    """Step-scoped entity output."
    
    Stores normalized entity-level results for a specific workflow step.
    Separates entity mentions from user-facing entity lists per step.
    """

    __tablename__ = "step_entity_outputs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(
        String, nullable=False, comment="Entity type: Insured, Carrier, etc."
    )
    entity_label: Mapped[str] = mapped_column(
        String, nullable=False, comment="Display label for the entity"
    )
    display_payload: Mapped[dict] = mapped_column(
        JSONB, nullable=False, comment="Normalized display payload"
    )
    confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4), nullable=True, comment="Overall confidence (0.0-1.0)"
    )
    source_section_extraction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("section_extractions.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )

    # Relationships
    document: Mapped["Document"] = relationship("Document")
    workflow: Mapped["Workflow"] = relationship("Workflow")
    section_extraction: Mapped["SectionExtraction | None"] = relationship("SectionExtraction")

    __table_args__ = (
        {"comment": "Step-scoped entity level outputs"},
    )


class WorkflowDocument(Base):
    """Join table for workflows and documents.
    
    This table acts as the linking entity between documents and workflows.
    The document_id and workflow_id are both primary keys.
    """

    __tablename__ = "workflow_documents"

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        primary_key=True
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
        primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()", onupdate=datetime.utcnow
    )

    # Relationships
    document: Mapped["Document"] = relationship(
        "Document", 
        back_populates="workflow_documents"
    )
    workflow: Mapped["Workflow | None"] = relationship(
        "Workflow", 
        back_populates="workflow_documents",
        foreign_keys=[workflow_id]
    )


class Workflow(Base):
    """Temporal workflow instances."""

    __tablename__ = "workflows"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workflow_definition_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workflow_definitions.id"), 
        nullable=True
    )
    workflow_name: Mapped[str] = mapped_column(
        String, 
        nullable=False, 
        default="Untitled"
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    temporal_workflow_id: Mapped[str | None] = mapped_column(
        String, 
        unique=True, 
        nullable=True
    )
    status: Mapped[str] = mapped_column(
        String, 
        nullable=False, 
        default="running"
    )  # running | completed | failed
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), 
        server_default="NOW()", 
        onupdate=datetime.utcnow
    )

    # Relationships
    workflow_definition: Mapped["WorkflowDefinition | None"] = relationship(
        "WorkflowDefinition", 
        back_populates="workflows"
    )
    events: Mapped[list["WorkflowRunEvent"]] = relationship(
        "WorkflowRunEvent", 
        back_populates="workflow", 
        cascade="all, delete-orphan"
    )
    stage_runs: Mapped[list["WorkflowStageRun"]] = relationship(
        "WorkflowStageRun", 
        back_populates="workflow", 
        cascade="all, delete-orphan"
    )
    workflow_documents: Mapped[list["WorkflowDocument"]] = relationship(
        "WorkflowDocument", 
        back_populates="workflow", 
        cascade="all, delete-orphan"
    )
    section_extractions: Mapped[list["SectionExtraction"]] = relationship(
        "SectionExtraction", 
        back_populates="workflow", 
        cascade="all, delete-orphan"
    )
    vector_embeddings: Mapped[list["VectorEmbedding"]] = relationship(
        "VectorEmbedding", back_populates="workflow", cascade="all, delete-orphan"
    )
    workflow_outputs: Mapped[list["WorkflowOutput"]] = relationship(
        "WorkflowOutput", back_populates="workflow", cascade="all, delete-orphan"
    )
    proposals: Mapped[list["Proposal"]] = relationship(
        "Proposal", back_populates="workflow", cascade="all, delete-orphan"
    )
    queries: Mapped[list["WorkflowQuery"]] = relationship(
        "WorkflowQuery", back_populates="workflow", cascade="all, delete-orphan"
    )


class WorkflowRunEvent(Base):
    """Audit trail for workflow runs."""

    __tablename__ = "workflow_run_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("workflows.id", ondelete="CASCADE"), 
        nullable=False
    )
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    event_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), 
        server_default="NOW()", 
        onupdate=datetime.utcnow
    )

    # Relationships
    workflow: Mapped["Workflow"] = relationship("Workflow", back_populates="events")


class WorkflowDefinition(Base):
    """Static workflow definitions."""

    __tablename__ = "workflow_definitions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workflow_key: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    supports_multi_docs: Mapped[bool] = mapped_column(Boolean, default=False)
    supported_steps: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()", onupdate=datetime.utcnow
    )

    # Relationships
    workflows: Mapped[list["Workflow"]] = relationship(
        "Workflow", 
        back_populates="workflow_definition"
    )
    workflow_outputs: Mapped[list["WorkflowOutput"]] = relationship(
        "WorkflowOutput", back_populates="workflow_definition"
    )



class WorkflowStageRun(Base):
    """Stages within a workflow execution."""

    __tablename__ = "workflow_stage_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("workflows.id", ondelete="CASCADE"), 
        nullable=False
    )
    stage_name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    started_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), 
        nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), 
        nullable=True
    )
    stage_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()", onupdate=datetime.utcnow
    )

    # Relationships
    workflow: Mapped["Workflow"] = relationship(
        "Workflow", 
        back_populates="stage_runs"
    )

    __table_args__ = (
        UniqueConstraint("workflow_id", "stage_name", name="uq_workflow_stage_run"),
    )


class WorkflowDocumentStageRun(Base):
    """Document-level stage tracking within a workflow."""
    
    __tablename__ = "workflow_document_stage_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    stage_name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="running")
    started_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    stage_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()", onupdate=datetime.utcnow
    )

    # Relationships
    document: Mapped["Document"] = relationship("Document", back_populates="stage_runs")
    workflow: Mapped["Workflow"] = relationship("Workflow")

    __table_args__ = (
        UniqueConstraint("workflow_id", "document_id", "stage_name", name="uq_workflow_doc_stage"),
        {"comment": "Document-level stage tracking within a workflow"},
    )


class WorkflowEntityScope(Base):
    """Entities scoped to a specific workflow run."""

    __tablename__ = "workflow_entity_scope"

    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), primary_key=True
    )
    canonical_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_entities.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()", onupdate=datetime.utcnow
    )


class WorkflowRelationshipScope(Base):
    """Relationships scoped to a specific workflow run."""

    __tablename__ = "workflow_relationship_scope"

    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), primary_key=True
    )
    relationship_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entity_relationships.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()", onupdate=datetime.utcnow
    )


class VectorEmbedding(Base):
    """Vector database for high-precision semantic recall."""

    __tablename__ = "vector_embeddings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )
    canonical_entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("canonical_entities.id", ondelete="SET NULL"),
        nullable=True,
        comment="FK to canonical entity for vector↔graph bridge"
    )
    source_chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_chunks.id", ondelete="SET NULL"), nullable=True,
        comment="FK to document_chunks for chunk-level embeddings"
    )
    section_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_id: Mapped[str] = mapped_column(String, nullable=False)
    embedding_model: Mapped[str] = mapped_column(String, nullable=False)
    embedding_dim: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding_version: Mapped[str] = mapped_column(String, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(384), nullable=True)
    effective_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    expiration_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    location_id: Mapped[str | None] = mapped_column(String, nullable=True)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="EMBEDDED")
    embedded_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )

    # Relationships
    document: Mapped["Document"] = relationship("Document", back_populates="vector_embeddings")
    workflow: Mapped["Workflow"] = relationship("Workflow", back_populates="vector_embeddings")
    canonical_entity: Mapped["CanonicalEntity | None"] = relationship(
        "CanonicalEntity",
        foreign_keys=[canonical_entity_id]
    )
    source_chunk: Mapped["DocumentChunk | None"] = relationship("DocumentChunk")

    __table_args__ = (
        {"comment": "Canonical table for pgvector embeddings"},
    )


class WorkflowOutput(Base):
    """Generic storage for all product workflow outputs.
    
    This table stores the final results of product workflows like Policy Comparison,
    Loss Run Analysis, etc. Each workflow type has its own result schema stored in
    the JSONB result field.
    """

    __tablename__ = "workflow_outputs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )
    workflow_definition_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflow_definitions.id", ondelete="SET NULL"), nullable=True
    )
    workflow_name: Mapped[str] = mapped_column(
        String, nullable=False, comment="Denormalized workflow name for quick queries"
    )
    status: Mapped[str] = mapped_column(
        String, nullable=False, comment="COMPLETED, COMPLETED_WITH_WARNINGS, FAILED, NEEDS_REVIEW"
    )
    confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4), nullable=True, comment="Overall confidence score (0.0-1.0)"
    )
    result: Mapped[dict] = mapped_column(
        JSONB, nullable=False, comment="Workflow-specific output payload"
    )
    output_metadata: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Additional context (HITL flags, warnings, etc.)"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()", onupdate=datetime.utcnow
    )

    # Relationships
    workflow: Mapped["Workflow"] = relationship("Workflow", back_populates="workflow_outputs")
    workflow_definition: Mapped["WorkflowDefinition | None"] = relationship(
        "WorkflowDefinition", back_populates="workflow_outputs"
    )

    __table_args__ = (
        {"comment": "Generic storage for all product workflow outputs"},
    )


class Proposal(Base):
    """Generated insurance proposals."""

    __tablename__ = "proposals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )
    insured_name: Mapped[str] = mapped_column(String, nullable=False)
    carrier_name: Mapped[str] = mapped_column(String, nullable=False)
    policy_type: Mapped[str] = mapped_column(String, nullable=False)
    executive_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # The full proposal object (JSON)
    proposal_json: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Path to the generated PDF in storage
    pdf_path: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()", onupdate=datetime.utcnow
    )

    # Relationships
    workflow: Mapped["Workflow"] = relationship("Workflow", back_populates="proposals")

    __table_args__ = (
        {"comment": "Generated insurance proposals with PDF links and executive summaries"},
    )


class Citation(Base):
    """Citation model for mapping extracted items to source PDF locations.

    Stores precise source mapping for extracted coverages, exclusions, and clauses.
    Supports multiple non-contiguous spans across pages (FR-2).
    """

    __tablename__ = "citations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )

    # Polymorphic reference to source item
    source_type: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="Type: effective_coverage, effective_exclusion, endorsement, condition"
    )
    source_id: Mapped[str] = mapped_column(
        String(255), nullable=False,
        comment="Canonical ID or stable ID of the source item"
    )

    # Location data - supports multiple spans (FR-2)
    spans: Mapped[list] = mapped_column(
        JSONB, nullable=False,
        comment="Array of span objects: [{page_number, bounding_boxes, text_content}]"
    )

    # Verbatim source text (FR-4)
    verbatim_text: Mapped[str] = mapped_column(
        Text, nullable=False,
        comment="Exact extracted policy language"
    )

    # Page metadata for quick navigation
    primary_page: Mapped[int] = mapped_column(
        Integer, nullable=False,
        comment="Primary page number (1-indexed) for initial navigation"
    )
    page_range: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True,
        comment="Page range: {start: int, end: int} for multi-page citations"
    )

    # Confidence and provenance
    extraction_confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4), nullable=True,
        comment="Confidence in source mapping accuracy (0.0-1.0)"
    )
    extraction_method: Mapped[str] = mapped_column(
        String(50), nullable=False, default="docling",
        comment="Method: docling, pdfplumber, manual"
    )

    # Clause-level authority (FR-3)
    clause_reference: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="Clause reference e.g., 'SECTION II.B.3' or 'Endorsement CA 20 48'"
    )

    # Citation resolution tracking (Phase 3)
    resolution_method: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
        comment="How citation was resolved: direct_text_match, semantic_chunk_match, placeholder"
    )

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )

    # Relationships
    document: Mapped["Document"] = relationship("Document", back_populates="citations")

    __table_args__ = (
        UniqueConstraint("document_id", "source_type", "source_id", name="uq_citation_source"),
        {"comment": "Citation source mapping for extracted items"},
    )


class WorkflowQuery(Base):
    """Persisted chat history for workflows."""

    __tablename__ = "workflow_queries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("workflows.id", ondelete="CASCADE"), 
        nullable=False
    )
    role: Mapped[str] = mapped_column(
        String, nullable=False, comment="user | model"
    )
    content: Mapped[str] = mapped_column(
        Text, nullable=False
    )
    additional_metadata: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="NOW()"
    )

    # Relationships
    workflow: Mapped["Workflow"] = relationship("Workflow", back_populates="queries")


