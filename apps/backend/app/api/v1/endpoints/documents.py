from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Annotated, List, Optional, Dict, Any

from app.core.database import get_async_session as get_session
from app.services.user_service import UserService
from app.services.document_service import DocumentService
from app.core.auth import get_current_user
from app.schemas.auth import CurrentUser
from app.schemas.generated.documents import (
    ApiResponse,
    DocumentResponse,
    MultipleDocumentResponse,
    EntityResponse,
    SectionResponse
)
from app.utils.logging import get_logger
from app.utils.responses import create_api_response, create_error_detail

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
    response_model=ApiResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload one or multiple documents",
    operation_id="upload_documents",
)
async def upload_documents(
    request: Request,
    files: List[UploadFile] = File(
        ..., 
        description="One or more documents to upload PDF"
    ),
    workflow_id: Optional[UUID] = Form(None),
    current_user: Annotated[CurrentUser, Depends(get_current_user)] = None,
    user_service: Annotated[UserService, Depends(get_user_service)] = None,
    document_service: Annotated[DocumentService, Depends(get_document_service)] = None,
) -> ApiResponse:
    """Upload one or multiple documents."""
    user = await user_service.get_or_create_user_from_jwt(current_user)
    result = await document_service.upload_documents(files, user.id, workflow_id)
    
    return create_api_response(
        data=result,
        message=f"Successfully uploaded {len(files)} documents",
        request=request
    )

@router.get(
    "/",
    response_model=ApiResponse,
    summary="List documents",
    operation_id="list_documents",
)
async def list_documents(
    request: Request,
    limit: int = Query(50),
    offset: int = Query(0),
    workflow_id: Optional[UUID] = Query(None),
    current_user: Annotated[CurrentUser, Depends(get_current_user)] = None,
    user_service: Annotated[UserService, Depends(get_user_service)] = None,
    document_service: Annotated[DocumentService, Depends(get_document_service)] = None,
) -> ApiResponse:
    """List documents for the current user."""
    user = await user_service.get_or_create_user_from_jwt(current_user)
    documents_data = await document_service.list_documents(
        user.id, limit=limit, offset=offset, workflow_id=workflow_id
    )
    
    return create_api_response(
        data=documents_data,
        message="Documents retrieved successfully",
        request=request
    )

@router.get(
    "/{document_id}",
    response_model=ApiResponse,
    summary="Get document details",
    operation_id="get_document",
)
async def get_document(
    request: Request,
    document_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)] = None,
    user_service: Annotated[UserService, Depends(get_user_service)] = None,
    document_service: Annotated[DocumentService, Depends(get_document_service)] = None,
) -> ApiResponse:
    """Retrieve document metadata by ID."""
    user = await user_service.get_or_create_user_from_jwt(current_user)
    
    document = await document_service.get_document(document_id, user.id)
    if not document:
        error_detail = create_error_detail(
            title="Document Not Found",
            status=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} not found",
            request=request
        )
        raise HTTPException(status_code=404, detail=error_detail.model_dump(mode='json'))
        
    return create_api_response(
        data=DocumentResponse(**document) if isinstance(document, dict) else document,
        message="Document details retrieved successfully",
        request=request
    )

@router.delete(
    "/{document_id}",
    response_model=ApiResponse,
    summary="Delete document",
    operation_id="delete_document",
)
async def delete_document(
    request: Request,
    document_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)] = None,
    user_service: Annotated[UserService, Depends(get_user_service)] = None,
    document_service: Annotated[DocumentService, Depends(get_document_service)] = None,
) -> ApiResponse:
    """Delete document and all related data."""
    user = await user_service.get_or_create_user_from_jwt(current_user)
    
    success = await document_service.delete_document(document_id, user.id)
    if not success:
        error_detail = create_error_detail(
            title="Document Not Found",
            status=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} not found",
            request=request
        )
        raise HTTPException(status_code=404, detail=error_detail.model_dump(mode='json'))
    
    return create_api_response(
        data=None,
        message="Document deleted successfully",
        request=request
    )

@router.get(
    "/{document_id}/entities",
    response_model=ApiResponse,
    summary="Get document entities",
    operation_id="get_document_entities",
)
async def get_document_entities(
    request: Request,
    document_id: UUID,
    entity_type: Optional[str] = None,
    current_user: Annotated[CurrentUser, Depends(get_current_user)] = None,
    user_service: Annotated[UserService, Depends(get_user_service)] = None,
    document_service: Annotated[DocumentService, Depends(get_document_service)] = None,
) -> ApiResponse:
    """Retrieve extracted entities for a document."""
    user = await user_service.get_or_create_user_from_jwt(current_user)
    
    result = await document_service.get_document_entities(document_id, user.id, entity_type)
    if not result:
        error_detail = create_error_detail(
            title="Document Not Found",
            status=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} not found",
            request=request
        )
        raise HTTPException(status_code=404, detail=error_detail.model_dump(mode='json'))
        
    return create_api_response(
        data=result,
        message="Document entities retrieved successfully",
        request=request
    )

@router.get(
    "/{document_id}/sections",
    response_model=ApiResponse,
    summary="Get document sections",
    operation_id="get_document_sections",
)
async def get_document_sections(
    request: Request,
    document_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)] = None,
    user_service: Annotated[UserService, Depends(get_user_service)] = None,
    document_service: Annotated[DocumentService, Depends(get_document_service)] = None,
) -> ApiResponse:
    """Retrieve structured sections for a document."""
    user = await user_service.get_or_create_user_from_jwt(current_user)
    
    result = await document_service.get_document_sections(document_id, user.id)
    if not result:
        error_detail = create_error_detail(
            title="Document Not Found",
            status=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} not found",
            request=request
        )
        raise HTTPException(status_code=404, detail=error_detail.model_dump(mode='json'))
        
    return create_api_response(
        data={"sections": result},
        message="Document sections retrieved successfully",
        request=request
    )