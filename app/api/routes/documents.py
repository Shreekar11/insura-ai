"""Document management API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.database.session import get_session
from app.debug import get_pipeline_status

router = APIRouter()


# Placeholder for future document CRUD operations
# TODO: Implement document management endpoints
# - GET /documents - List all documents
# - GET /documents/{document_id} - Get document details
# - POST /documents - Create new document
# - PUT /documents/{document_id} - Update document
# - DELETE /documents/{document_id} - Delete document

@router.get("/documents/{document_id}/pipeline-status")
async def pipeline_status(document_id: UUID, session: AsyncSession = Depends(get_session)):
    """Get complete pipeline status for debugging."""
    status = await get_pipeline_status(session, document_id)
    if "error" in status:
        raise HTTPException(status_code=404, detail=status["error"])
    return status

