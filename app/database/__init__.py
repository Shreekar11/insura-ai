"""Database module for SQLAlchemy models and session management."""

from app.database.base import Base, engine, get_db_session
from app.database.client import DatabaseClient, db_client, init_database, close_database
from app.database.models import (
    Claim,
    Document,
    DocumentClassification,
    DocumentPage,
    DocumentRawText,
    ExtractedField,
    FinancialAnalysis,
    OCRResult,
    OCRToken,
    PolicyComparison,
    Proposal,
    PropertySOV,
    Quote,
    Submission,
    User,
    Workflow,
    WorkflowRunEvent,
)
from app.database.session import get_async_session

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
    "DocumentRawText",
    "OCRResult",
    "OCRToken",
    "DocumentClassification",
    "ExtractedField",
    "Workflow",
    "WorkflowRunEvent",
    "Submission",
    "PolicyComparison",
    "Claim",
    "Quote",
    "Proposal",
    "FinancialAnalysis",
    "PropertySOV",
]

