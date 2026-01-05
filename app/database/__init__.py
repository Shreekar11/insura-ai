"""Database module for SQLAlchemy models and session management."""

from app.core.database import Base, engine, get_db_session
from app.core.database import DatabaseClient, db_client, init_database, close_database
from app.database.models import (
    Document,
    DocumentChunk,
    DocumentPage,
    WorkflowDocumentStageRun,
    DocumentTable,
    CanonicalEntity,
    EntityAttribute,
    EntityEvidence,
    EntityMention,
    PageAnalysis,
    PageClassificationResult,
    PageManifestRecord,
    SectionExtraction,
    StepEntityOutput,
    StepSectionOutput,
    User,
    Workflow,
    WorkflowRunEvent,
)
from app.core.database import get_async_session

__all__ = [
    "Base",
    "engine",
    "get_db_session",
    "get_async_session",
    "DatabaseClient",
    "db_client",
    "init_database",
    "close_database",
    "User",
    "Document",
    "DocumentPage",
    "DocumentChunk",
    "WorkflowDocumentStageRun",
    "DocumentTable",
    "PageAnalysis",
    "PageClassificationResult",
    "PageManifestRecord",
    "SectionExtraction",
    "CanonicalEntity",
    "EntityMention",
    "EntityEvidence",
    "EntityAttribute",
    "StepSectionOutput",
    "StepEntityOutput",
    "Workflow",
    "WorkflowRunEvent",
]

