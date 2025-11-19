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
)
from sqlalchemy.dialects.postgresql import UUID
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
    )  # rules | gpt_zero_shot | claude_zero_shot | mistral_zero_shot
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

