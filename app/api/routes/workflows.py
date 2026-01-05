from typing import Annotated, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, HttpUrl
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.services.workflow_service import WorkflowService
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)

router = APIRouter()

class WorkflowExtractionRequest(BaseModel):
    pdf_url: HttpUrl

class WorkflowExtractionResponse(BaseModel):
    workflow_id: str
    documents: List[str]
    temporal_id: str
    status: str
    message: str

@router.post(
    "/extract",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=WorkflowExtractionResponse,
    summary="Start document processing workflow",
    description="Create a document record and start async Temporal workflow for OCR extraction, normalization, and entity resolution.",
    operation_id="start_document_workflow",
)
async def document_extraction(
    request: WorkflowExtractionRequest,
    db_session: Annotated[AsyncSession, Depends(get_async_session)],
) -> WorkflowExtractionResponse:
    """Start async document extraction workflow."""
    
    # TODO: Replace with auth-derived user
    DEFAULT_TEST_USER_ID = UUID("00000000-0000-0000-0000-000000000001")

    try:
        workflow_service = WorkflowService(db_session)
        result = await workflow_service.start_extraction_workflow(
            pdf_url=str(request.pdf_url),
            user_id=DEFAULT_TEST_USER_ID
        )
        return WorkflowExtractionResponse(**result)

    except Exception as e:
        LOGGER.error(
            "Failed to start document extraction workflow",
            exc_info=True,
            extra={"pdf_url": str(request.pdf_url), "error": str(e)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "WorkflowStartError",
                "message": "Failed to start document extraction workflow",
                "detail": str(e),
            },
        )


@router.get(
    "/status/{workflow_id}",
    status_code=status.HTTP_200_OK,
    summary="Get workflow status",
    description="Query the current status and progress of a document processing workflow.",
    operation_id="get_workflow_status",
)
async def get_workflow_status(
    workflow_id: str,
    db_session: Annotated[AsyncSession, Depends(get_async_session)]
) -> dict:
    """Get workflow execution status and progress."""
    try:
        workflow_service = WorkflowService(db_session)
        return await workflow_service.get_workflow_status(workflow_id)
    except Exception as e:
        LOGGER.error(
            "Failed to query workflow status",
            exc_info=True,
            extra={"workflow_id": workflow_id, "error": str(e)},
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "WorkflowNotFound",
                "message": "Workflow not found or query failed",
                "detail": str(e),
            },
        )


@router.get(
    "/stages",
    status_code=status.HTTP_200_OK,
    summary="Get all document stages",
    description="Get the completion status of all processing stages for all documents.",
)
async def get_all_document_stages(
    db_session: Annotated[AsyncSession, Depends(get_async_session)]
):
    """Get the completion status of all processing stages for all documents."""
    try: 
        workflow_service = WorkflowService(db_session)
        return await workflow_service.get_all_document_stages()
    except Exception as e:
        LOGGER.error("Failed to get all document stages", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=str(e)
        )


@router.get(
    "/stages/{document_id}",
    status_code=status.HTTP_200_OK,
    summary="Get document stages",
    description="Get the completion status of all processing stages for a specific document.",
)
async def get_document_stages(
    document_id: UUID,
    db_session: Annotated[AsyncSession, Depends(get_async_session)],
    workflow_id: Optional[UUID] = None,
):
    """Get the completion status of all processing stages for a document."""
    try:
        workflow_service = WorkflowService(db_session)
        return await workflow_service.get_document_stage(document_id, workflow_id)
    except Exception as e:
        LOGGER.error("Failed to get document stages", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=str(e)
        )
