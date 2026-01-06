"""Document management API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.core.database import get_async_session as get_session
from app.repositories.document_repository import DocumentRepository
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)

router = APIRouter()


# Placeholder for future document CRUD operations
# TODO: Implement document management endpoints
# - GET /documents - List all documents
# - GET /documents/{document_id} - Get document details
# - POST /documents - Create new document
# - PUT /documents/{document_id} - Update document
# - DELETE /documents/{document_id} - Delete document

@router.get("/{document_id}/status")
async def pipeline_status(document_id: UUID, session: AsyncSession = Depends(get_session)):
    document_repository = DocumentRepository(session)
    result = await document_repository.get_by_id(document_id)

    LOGGER.info("Document: %s", result)

    return {
        "id": result.id,
        "status": result.status,
        "file_path": result.file_path,
        "created_at": result.uploaded_at.isoformat() if result.uploaded_at else None,
        "updated_at": result.updated_at.isoformat() if result.updated_at else None,
    }