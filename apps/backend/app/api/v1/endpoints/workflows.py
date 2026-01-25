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
    ApiResponse,
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
from app.utils.responses import create_api_response, create_error_detail

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
    response_model=ApiResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Execute a product workflow",
    operation_id="execute_workflow",
)
async def execute_workflow(
    request: Request,
    workflow_name: Annotated[str, Form()],
    workflow_definition_id: Annotated[str, Form()],
    file1: Annotated[UploadFile, File()],
    file2: Annotated[Optional[UploadFile], File()] = None,
    current_user: Annotated[CurrentUser, Depends(get_current_user)] = None,
    user_service: Annotated[UserService, Depends(get_user_service)] = None,
    workflow_service: Annotated[WorkflowService, Depends(get_workflow_service)] = None,
    metadata_json: Annotated[Optional[str], Form()] = None,
) -> ApiResponse:
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
        
        data = WorkflowExecutionResponse(
            workflow_id=result["workflow_id"]
        )
        
        return create_api_response(
            data=data,
            message=result["message"],
            request=request
        )

    except Exception as e:
        LOGGER.error(f"Workflow execution failed: {e}", exc_info=True)
        error_detail = create_error_detail(
            title="Workflow Execution Failed",
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
            request=request
        )
        raise HTTPException(status_code=500, detail=error_detail.model_dump())


@router.get(
    "/",
    response_model=ApiResponse,
    summary="List workflows",
    operation_id="list_workflows",
)
async def list_workflows(
    request: Request,
    limit: int = Query(50),
    offset: int = Query(0),
    current_user: Annotated[CurrentUser, Depends(get_current_user)] = None,
    user_service: Annotated[UserService, Depends(get_user_service)] = None,
    workflow_service: Annotated[WorkflowService, Depends(get_workflow_service)] = None,
) -> ApiResponse:
    """List workflow executions for the current user."""
    user = await user_service.get_or_create_user_from_jwt(current_user)
    
    workflows_data = await workflow_service.list_workflows(user.id, limit=limit, offset=offset)

    if not workflows_data or not workflows_data.get("workflows"):
        error_detail = create_error_detail(
            title="Workflows Not Found",
            status=status.HTTP_404_NOT_FOUND,
            detail="No workflows found for the current user",
            request=request
        )
        raise HTTPException(status_code=404, detail=error_detail.model_dump())

    data = WorkflowListResponse(
        total=workflows_data["total"],
        workflows=workflows_data["workflows"],
    )
    
    return create_api_response(
        data=data,
        message="Workflows retrieved successfully",
        request=request
    )

@router.get(
    "/definitions",
    response_model=ApiResponse,
    summary="Get workflow definitions",
    operation_id="get_workflow_definitions",
)
async def get_workflow_definitions(
    request: Request,
    workflow_service: Annotated[WorkflowService, Depends(get_workflow_service)] = None,
) -> ApiResponse:
    """Retrieve all available workflow definitions."""
    definitions = await workflow_service.list_definitions()
    return create_api_response(
        data={"definitions": definitions},
        message="Workflow definitions retrieved successfully",
        request=request
    )


@router.get(
    "/{workflow_id}",
    response_model=ApiResponse,
    summary="Get workflow details",
    operation_id="get_workflow",
)
async def get_workflow(
    request: Request,
    workflow_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)] = None,
    user_service: Annotated[UserService, Depends(get_user_service)] = None,
    workflow_service: Annotated[WorkflowService, Depends(get_workflow_service)] = None,
) -> ApiResponse:
    """Retrieve details of a specific workflow execution."""
    user = await user_service.get_or_create_user_from_jwt(current_user)
    
    wf = await workflow_service.get_workflow_details(workflow_id, user.id)
    if not wf:
        error_detail = create_error_detail(
            title="Workflow Not Found",
            status=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with ID {workflow_id} not found",
            request=request
        )
        raise HTTPException(status_code=404, detail=error_detail.model_dump())
        
    return create_api_response(
        data=WorkflowResponse(**wf) if isinstance(wf, dict) else wf,
        message="Workflow details retrieved successfully",
        request=request
    )


@router.get(
    "/{workflow_id}/status",
    response_model=ApiResponse,
    summary="Get workflow status",
    operation_id="get_workflow_status",
)
async def get_workflow_status(
    request: Request,
    workflow_id: str,
    workflow_service: Annotated[WorkflowService, Depends(get_workflow_service)] = None,
) -> ApiResponse:
    """Check current workflow status and progress from Temporal."""
    status_data = await workflow_service.execute_get_status(workflow_id)
    return create_api_response(
        data=status_data,
        message="Workflow status retrieved successfully",
        request=request
    )


@router.get(
    "/{workflow_id}/extracted/{document_id}",
    response_model=ApiResponse,
    summary="Get extracted data",
    operation_id="get_extracted_data",
)
async def get_extracted_data(
    request: Request,
    workflow_id: UUID,
    document_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)] = None,
    user_service: Annotated[UserService, Depends(get_user_service)] = None,
    workflow_service: Annotated[WorkflowService, Depends(get_workflow_service)] = None,
) -> ApiResponse:
    """Retrieve extraction results for a document within a workflow."""
    user = await user_service.get_or_create_user_from_jwt(current_user)
    
    result = await workflow_service.get_workflow_extraction(workflow_id, document_id, user.id)
    if not result:
        error_detail = create_error_detail(
            title="Extracted Data Not Found",
            status=status.HTTP_404_NOT_FOUND,
            detail=f"Extraction results not found for document {document_id} in workflow {workflow_id}",
            request=request
        )
        raise HTTPException(status_code=404, detail=error_detail.model_dump())
        
    return create_api_response(
        data=result,
        message="Extracted data retrieved successfully",
        request=request
    )


# Maintain backward compatibility for extraction endpoint if needed
@router.post(
    "/extract",
    response_model=ApiResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start document extraction",
    operation_id="start_extraction",
)
async def start_extraction(
    request: Request,
    extract_request: WorkflowExtractRequest,
    workflow_service: Annotated[WorkflowService, Depends(get_workflow_service)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    user_service: Annotated[UserService, Depends(get_user_service)],
) -> ApiResponse:
    """Start document extraction workflow."""
    user = await user_service.get_or_create_user_from_jwt(current_user)
    result = await workflow_service.execute_start_extraction(
        pdf_url=extract_request.pdf_url,
        user_id=user.id
    )
    
    data = WorkflowExecutionResponse(
        workflow_id=result["workflow_id"]
    )
    
    return create_api_response(
        data=data,
        message="Extraction workflow started successfully",
        request=request
    )
