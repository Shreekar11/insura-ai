from typing import Annotated, Any, Dict, List, Optional
from uuid import UUID
import json

from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session as get_session
from app.services.workflow_service import WorkflowService
from app.services.user_service import UserService
from app.core.auth import get_current_user
from app.schemas.auth import CurrentUser
from app.schemas.generated.workflows import (
    WorkflowExecutionResponse, 
    WorkflowResponse,
    WorkflowListResponse,
    WorkflowExecutionRequest,
    WorkflowExtractRequest,
    WorkflowDefinitionResponse,
    WorkflowStatusResponse,
    WorkflowExtractedDataResponse
)
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)

router = APIRouter()

async def get_workflow_service(
    db_session: Annotated[AsyncSession, Depends(get_session)]
) -> WorkflowService:
    return WorkflowService(db_session)

async def get_user_service(
    db_session: Annotated[AsyncSession, Depends(get_session)]
) -> UserService:
    return UserService(db_session)


@router.post(
    "/execute",
    response_model=WorkflowExecutionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Execute a product workflow",
    operation_id="execute_workflow",
)
async def execute_workflow(
    workflow_name: Annotated[str, Form()],
    workflow_definition_id: Annotated[str, Form()],
    file1: Annotated[UploadFile, File()],
    file2: Annotated[Optional[UploadFile], File()] = None,
    current_user: Annotated[CurrentUser, Depends(get_current_user)] = None,
    user_service: Annotated[UserService, Depends(get_user_service)] = None,
    workflow_service: Annotated[WorkflowService, Depends(get_workflow_service)] = None,
    metadata_json: Annotated[Optional[str], Form()] = None,
) -> WorkflowExecutionResponse:
    """Execute a product-specific workflow (e.g., policy comparison)."""
    user = await user_service.get_or_create_user_from_jwt(current_user)
    
    try:
        metadata = json.loads(metadata_json) if metadata_json else {}
        files = [file for file in [file1, file2] if file]
        
        result = await workflow_service.submit_product_workflow(
            workflow_name=workflow_name,
            workflow_definition_id=workflow_definition_id,
            files=files,
            user_id=user.id,
            metadata=metadata
        )
        
        return WorkflowExecutionResponse(
            workflow_id=result["workflow_id"],
            status=result["status"],
            created_at=str(result.get("created_at", "")),
            message=result["message"]
        )

    except Exception as e:
        LOGGER.error(f"Workflow execution failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/",
    response_model=WorkflowListResponse,
    summary="List workflows",
    operation_id="list_workflows",
)
async def list_workflows(
    limit: int = Query(50),
    offset: int = Query(0),
    current_user: Annotated[CurrentUser, Depends(get_current_user)] = None,
    user_service: Annotated[UserService, Depends(get_user_service)] = None,
    workflow_service: Annotated[WorkflowService, Depends(get_workflow_service)] = None,
) -> WorkflowListResponse:
    """List workflow executions for the current user."""
    user = await user_service.get_or_create_user_from_jwt(current_user)
    return await workflow_service.list_workflows(user.id, limit=limit, offset=offset)


@router.get(
    "/definitions",
    response_model=List[WorkflowDefinitionResponse],
    summary="Get workflow definitions",
    operation_id="get_workflow_definitions",
)
async def get_workflow_definitions(
    workflow_service: Annotated[WorkflowService, Depends(get_workflow_service)] = None,
) -> List[WorkflowDefinitionResponse]:
    """Retrieve all available workflow definitions."""
    return await workflow_service.list_definitions()


@router.get(
    "/{workflow_id}",
    response_model=WorkflowResponse,
    summary="Get workflow details",
    operation_id="get_workflow",
)
async def get_workflow(
    workflow_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)] = None,
    user_service: Annotated[UserService, Depends(get_user_service)] = None,
    workflow_service: Annotated[WorkflowService, Depends(get_workflow_service)] = None,
):
    """Retrieve details of a specific workflow execution."""
    user = await user_service.get_or_create_user_from_jwt(current_user)
    
    wf = await workflow_service.get_workflow_details(workflow_id, user.id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
        
    return wf


@router.get(
    "/{workflow_id}/status",
    response_model=WorkflowStatusResponse,
    summary="Get workflow status",
    operation_id="get_workflow_status",
)
async def get_workflow_status(
    workflow_id: str,
    workflow_service: Annotated[WorkflowService, Depends(get_workflow_service)] = None,
) -> WorkflowStatusResponse:
    """Check current workflow status and progress from Temporal."""
    return await workflow_service.execute_get_status(workflow_id)


@router.get(
    "/{workflow_id}/extracted/{document_id}",
    response_model=WorkflowExtractedDataResponse,
    summary="Get extracted data",
    operation_id="get_extracted_data",
)
async def get_extracted_data(
    workflow_id: UUID,
    document_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)] = None,
    user_service: Annotated[UserService, Depends(get_user_service)] = None,
    workflow_service: Annotated[WorkflowService, Depends(get_workflow_service)] = None,
) -> WorkflowExtractedDataResponse:
    """Retrieve extraction results for a document within a workflow."""
    user = await user_service.get_or_create_user_from_jwt(current_user)
    
    result = await workflow_service.get_workflow_extraction(workflow_id, document_id, user.id)
    if not result:
        raise HTTPException(status_code=404, detail="Workflow not found")
        
    return result


# Maintain backward compatibility for extraction endpoint if needed
@router.post(
    "/extract",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start document extraction",
    operation_id="start_extraction",
)
async def start_extraction(
    request: WorkflowExtractRequest,
    workflow_service: Annotated[WorkflowService, Depends(get_workflow_service)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    user_service: Annotated[UserService, Depends(get_user_service)],
):
    """Start document extraction workflow."""
    user = await user_service.get_or_create_user_from_jwt(current_user)
    result = await workflow_service.execute_start_extraction(
        pdf_url=request.pdf_url,
        user_id=user.id
    )
    return result
