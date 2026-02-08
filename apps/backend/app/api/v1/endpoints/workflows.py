from typing import Annotated, Any, Dict, List, Optional
from uuid import UUID
import json

from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session as get_session
from app.services.workflow_service import WorkflowService
from app.services.user_service import UserService
from app.core.auth import get_current_user, get_current_user_from_query
from app.schemas.auth import CurrentUser
from app.schemas.generated.workflows import (
    ApiResponse,
    WorkflowExecutionResponse, 
    WorkflowResponse,
    WorkflowListResponse,
    WorkflowExecutionRequest,
    WorkflowCreateRequest,
    WorkflowExtractRequest,
    WorkflowDefinitionResponse,
    WorkflowStatusResponse,
    WorkflowStatusResponse,
    WorkflowExtractedDataResponse,
    WorkflowUpdateRequest
)
from app.utils.logging import get_logger
from app.utils.responses import create_api_response, create_error_detail
from app.services.sse_manager import SSEManager

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
    payload: WorkflowExecutionRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)] = None,
    user_service: Annotated[UserService, Depends(get_user_service)] = None,
    workflow_service: Annotated[WorkflowService, Depends(get_workflow_service)] = None,
) -> ApiResponse:
    """Execute a product-specific workflow (e.g., policy comparison)."""
    user = await user_service.get_or_create_user_from_jwt(current_user)
    
    try:
        result = await workflow_service.submit_product_workflow(
            workflow_name=payload.workflow_name,
            workflow_definition_id=str(payload.workflow_definition_id),
            document_ids=payload.document_ids or [],
            user_id=user.id,
            metadata=payload.metadata,
            workflow_id=payload.workflow_id
        )
        
        data = WorkflowExecutionResponse(
            workflow_id=result["workflow_id"],
            stream_url=f"/api/v1/workflows/stream/{result['workflow_id']}"
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
        raise HTTPException(status_code=500, detail=error_detail.model_dump(mode='json'))


@router.post(
    "/",
    response_model=ApiResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a draft workflow",
    operation_id="create_workflow",
)
async def create_workflow(
    request: Request,
    create_req: WorkflowCreateRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)] = None,
    user_service: Annotated[UserService, Depends(get_user_service)] = None,
    workflow_service: Annotated[WorkflowService, Depends(get_workflow_service)] = None,
) -> ApiResponse:
    """Create a draft workflow instance."""
    user = await user_service.get_or_create_user_from_jwt(current_user)

    LOGGER.info(f"Creating workflow for user: {user.id}")
    
    result = await workflow_service.execute_create_workflow(
        workflow_definition_id=create_req.workflow_definition_id,
        user_id=user.id,
        workflow_name=create_req.workflow_name
    )
    
    data = WorkflowExecutionResponse(
        workflow_id=result["workflow_id"]
    )
    
    return create_api_response(
        data=data,
        message=result["message"],
        request=request
    )


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
    include_documents: bool = Query(True),
    include_stages: bool = Query(True),
    include_events: bool = Query(True),
    events_limit: int = Query(5),
    current_user: Annotated[CurrentUser, Depends(get_current_user)] = None,
    user_service: Annotated[UserService, Depends(get_user_service)] = None,
    workflow_service: Annotated[WorkflowService, Depends(get_workflow_service)] = None,
) -> ApiResponse:
    """List workflow executions for the current user."""
    user = await user_service.get_or_create_user_from_jwt(current_user)
    
    workflows_data = await workflow_service.list_workflows(
        user.id, 
        limit=limit, 
        offset=offset,
        include_documents=include_documents,
        include_stages=include_stages,
        include_events=include_events,
        events_limit=events_limit
    )

    if not workflows_data or not workflows_data.get("workflows"):
        data = WorkflowListResponse(total=0, workflows=[])
        return create_api_response(
            data=data,
            message="No workflows found",
            request=request
        )

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
    "/all/{workflow_definition_id}",
    response_model=ApiResponse,
    summary="Get all workflows for a workflow definition",
    operation_id="get_all_workflows",
)
async def get_all_workflows(
    request: Request,
    workflow_definition_id: UUID,
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: Annotated[CurrentUser, Depends(get_current_user)] = None,
    user_service: Annotated[UserService, Depends(get_user_service)] = None,
    workflow_service: Annotated[WorkflowService, Depends(get_workflow_service)] = None,
) -> ApiResponse:
    """Retrieve details of a specific workflow execution."""
    user = await user_service.get_or_create_user_from_jwt(current_user)
    
    result = await workflow_service.get_all_workflows(
        workflow_definition_id=workflow_definition_id, 
        user_id=user.id,
        limit=limit,
        offset=offset
    )
    
    data = WorkflowListResponse(
        total=result["total"],
        workflows=result["workflows"],
    )
        
    return create_api_response(
        data=data,
        message="Workflows for the given workflow definition retrieved successfully",
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
    "/definitions/{workflow_definition_id}",     
    response_model=ApiResponse,
    summary="Get workflow definition by id",
    operation_id="get_workflow_definition_by_id"
)
async def get_workflow_definition_by_id(
    request: Request,
    workflow_definition_id: UUID,
    workflow_service: Annotated[WorkflowService, Depends(get_workflow_service)] = None,
) -> ApiResponse:
    """Retrieve workflow definition by id"""
    definition = await workflow_service.fetch_definition_by_id(workflow_definition_id)
    if not definition:
        error_detail = create_error_detail(
            title="Workflow definition Not Found",
            status=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow definition with ID {workflow_definition_id} not found",
            request=request
        )
        raise HTTPException(status_code=404, detail=error_detail.model_dump(mode='json'))
        
    return create_api_response(
        data={"definition": definition},
        message="Workflow definition details retrieved successfully",
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
        raise HTTPException(status_code=404, detail=error_detail.model_dump(mode='json'))
        
    return create_api_response(
        data=WorkflowResponse(**wf) if isinstance(wf, dict) else wf,
        message="Workflow details retrieved successfully",
        request=request
    )


@router.put(
    "/{workflow_id}",
    response_model=ApiResponse,
    summary="Update workflow",
    operation_id="update_workflow",
)
async def update_workflow(
    request: Request,
    payload: WorkflowUpdateRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)] = None,
    user_service: Annotated[UserService, Depends(get_user_service)] = None,
    workflow_service: Annotated[WorkflowService, Depends(get_workflow_service)] = None,
) -> ApiResponse:
    """Update workflow details (e.g. name)."""
    user = await user_service.get_or_create_user_from_jwt(current_user)

    wf = await workflow_service.execute_update_workflow(
        workflow_id=payload.workflow_id,
        workflow_name=payload.workflow_name,
        user_id=user.id
    )
    
    return create_api_response(
        data=WorkflowResponse(**wf) if isinstance(wf, dict) else wf,
        message="Workflow updated successfully",
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
        raise HTTPException(status_code=404, detail=error_detail.model_dump(mode='json'))
        
    return create_api_response(
        data=result,
        message="Extracted data retrieved successfully",
        request=request
    )


@router.get(
    "/{workflow_id}/comparison",
    response_model=ApiResponse,
    summary="Get entity comparison results",
    operation_id="get_entity_comparison",
)
async def get_entity_comparison(
    request: Request,
    workflow_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)] = None,
    user_service: Annotated[UserService, Depends(get_user_service)] = None,
    workflow_service: Annotated[WorkflowService, Depends(get_workflow_service)] = None,
) -> ApiResponse:
    """Retrieve entity-level comparison results for a workflow.

    Returns comparison of coverages and exclusions between two policy documents.
    """
    user = await user_service.get_or_create_user_from_jwt(current_user)

    result = await workflow_service.get_entity_comparison(workflow_id, user.id)
    if not result:
        error_detail = create_error_detail(
            title="Comparison Results Not Found",
            status=status.HTTP_404_NOT_FOUND,
            detail=f"Entity comparison results not found for workflow {workflow_id}",
            request=request
        )
        raise HTTPException(status_code=404, detail=error_detail.model_dump(mode='json'))

    return create_api_response(
        data=result,
        message="Entity comparison retrieved successfully",
        request=request
    )


@router.get(
    "/{workflow_id}/proposal",
    response_model=ApiResponse,
    summary="Get proposal results",
    operation_id="get_proposal",
)
async def get_proposal(
    request: Request,
    workflow_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)] = None,
    user_service: Annotated[UserService, Depends(get_user_service)] = None,
    workflow_service: Annotated[WorkflowService, Depends(get_workflow_service)] = None,
) -> ApiResponse:
    """Retrieve proposal generation results for a workflow."""
    user = await user_service.get_or_create_user_from_jwt(current_user)

    result = await workflow_service.get_proposal(workflow_id, user.id)
    if not result:
        error_detail = create_error_detail(
            title="Proposal Results Not Found",
            status=status.HTTP_404_NOT_FOUND,
            detail=f"Proposal results not found for workflow {workflow_id}",
            request=request
        )
        raise HTTPException(status_code=404, detail=error_detail.model_dump(mode='json'))

    return create_api_response(
        data=result,
        message="Proposal retrieved successfully",
        request=request
    )


@router.post(
    "/{workflow_id}/comparison",
    response_model=ApiResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Execute entity comparison",
    operation_id="execute_entity_comparison",
)
async def execute_entity_comparison(
    request: Request,
    workflow_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)] = None,
    user_service: Annotated[UserService, Depends(get_user_service)] = None,
    workflow_service: Annotated[WorkflowService, Depends(get_workflow_service)] = None,
) -> ApiResponse:
    """Execute entity-level comparison for a workflow.

    Compares coverages and exclusions between two policy documents.
    Emits a comparison:completed SSE event when done.
    """
    user = await user_service.get_or_create_user_from_jwt(current_user)

    result = await workflow_service.execute_entity_comparison(workflow_id, user.id)
    if not result:
        error_detail = create_error_detail(
            title="Comparison Failed",
            status=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to execute entity comparison for workflow {workflow_id}",
            request=request
        )
        raise HTTPException(status_code=400, detail=error_detail.model_dump(mode='json'))

    return create_api_response(
        data=result,
        message="Entity comparison completed successfully",
        request=request
    )


@router.get(
    "/stream/{workflow_id}",
    summary="Stream workflow events via SSE",
    operation_id="stream_workflow_events",
)
async def stream_workflow_events(
    workflow_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user_from_query)],
) -> StreamingResponse:
    """Stream real-time workflow events for a given workflow execution."""
    sse_manager = SSEManager()
    return StreamingResponse(
        sse_manager.stream_workflow_events(workflow_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable proxy buffering (Nginx)
        },
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
