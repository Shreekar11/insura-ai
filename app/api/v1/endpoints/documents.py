from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Annotated, List, Optional, Dict, Any

from app.core.database import get_async_session as get_session
from app.services.user_service import UserService
from app.services.document_service import DocumentService
from app.core.auth import get_current_user
from app.schemas.auth import CurrentUser
from app.schemas.generated.documents import (
    DocumentResponse,
    MultiDocumentResponse,
    EntityResponse,
    SectionResponse
)
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)

router = APIRouter()

async def get_user_service(
    db_session: Annotated[AsyncSession, Depends(get_session)]
) -> UserService:
    return UserService(db_session)

async def get_document_service(
    db_session: Annotated[AsyncSession, Depends(get_session)]
) -> DocumentService:
    return DocumentService(db_session)

@router.post(
    "/upload",
    response_model=MultiDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload one or multiple documents",
    operation_id="upload_documents",
)
async def upload_documents(
    files: List[UploadFile] = File(
        ..., 
        description="One or more documents to upload (PDF, images, etc.)"
    ),
    current_user: Annotated[CurrentUser, Depends(get_current_user)] = None,
    user_service: Annotated[UserService, Depends(get_user_service)] = None,
    document_service: Annotated[DocumentService, Depends(get_document_service)] = None,
) -> MultiDocumentResponse:
    """
    Upload one or multiple documents.
    
    This endpoint accepts multiple file uploads and processes them individually.
    Each document is uploaded to storage, recorded in the database, and returned in the summary.
    """
    # 1. Map to internal user
    user = await user_service.get_or_create_user_from_jwt(current_user)
    
    # 2. Delegate to service
    return await document_service.upload_documents(files, user.id)

@router.get(
    "/",
    summary="List documents",
    operation_id="list_documents",
)
async def list_documents(
    limit: int = Query(50),
    offset: int = Query(0),
    current_user: Annotated[CurrentUser, Depends(get_current_user)] = None,
    user_service: Annotated[UserService, Depends(get_user_service)] = None,
    document_service: Annotated[DocumentService, Depends(get_document_service)] = None,
):
    """List documents for the current user."""
    user = await user_service.get_or_create_user_from_jwt(current_user)
    return await document_service.list_documents(user.id, limit=limit, offset=offset)

@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Get document details",
    operation_id="get_document",
)
async def get_document(
    document_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)] = None,
    user_service: Annotated[UserService, Depends(get_user_service)] = None,
    document_service: Annotated[DocumentService, Depends(get_document_service)] = None,
):
    """Retrieve document metadata by ID."""
    user = await user_service.get_or_create_user_from_jwt(current_user)
    
    document = await document_service.get_document(document_id, user.id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
        
    return document

@router.delete(
    "/{document_id}",
    summary="Delete document",
    operation_id="delete_document",
)
async def delete_document(
    document_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)] = None,
    user_service: Annotated[UserService, Depends(get_user_service)] = None,
    document_service: Annotated[DocumentService, Depends(get_document_service)] = None,
):
    """Delete document and all related data."""
    user = await user_service.get_or_create_user_from_jwt(current_user)
    
    success = await document_service.delete_document(document_id, user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return {"message": "Document deleted", "status": "success"}

@router.get(
    "/{document_id}/entities",
    summary="Get document entities",
    operation_id="get_document_entities",
)
async def get_document_entities(
    document_id: UUID,
    entity_type: Optional[str] = None,
    current_user: Annotated[CurrentUser, Depends(get_current_user)] = None,
    user_service: Annotated[UserService, Depends(get_user_service)] = None,
    document_service: Annotated[DocumentService, Depends(get_document_service)] = None,
):
    """Retrieve extracted entities for a document."""
    user = await user_service.get_or_create_user_from_jwt(current_user)
    
    result = await document_service.get_document_entities(document_id, user.id, entity_type)
    if not result:
        raise HTTPException(status_code=404, detail="Document not found")
        
    return result

@router.get(
    "/{document_id}/sections",
    summary="Get document sections",
    operation_id="get_document_sections",
)
async def get_document_sections(
    document_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)] = None,
    user_service: Annotated[UserService, Depends(get_user_service)] = None,
    document_service: Annotated[DocumentService, Depends(get_document_service)] = None,
):
    """Retrieve structured sections for a document."""
    user = await user_service.get_or_create_user_from_jwt(current_user)
    
    result = await document_service.get_document_sections(document_id, user.id)
    if not result:
        raise HTTPException(status_code=404, detail="Document not found")
        
    return result