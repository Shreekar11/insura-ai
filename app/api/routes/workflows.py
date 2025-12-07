"""Workflow orchestration API endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.request.ocr import OCRExtractionRequest
from app.models.response.ocr import ErrorResponse
from app.config import settings
from app.database import get_async_session
from app.repositories.document_repository import DocumentRepository
from app.temporal_client import get_temporal_client
from app.temporal.workflows.process_document import ProcessDocumentWorkflow
from app.utils.exceptions import (
    OCRExtractionError,
    OCRTimeoutError,
    InvalidDocumentError,
    APIClientError,
)
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)

router = APIRouter()

@router.post(
    "/extract",
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        202: {
            "description": "Workflow started successfully",
        },
        400: {
            "description": "Invalid request",
            "model": ErrorResponse,
        },
        500: {
            "description": "Internal server error",
            "model": ErrorResponse,
        },
    },
    summary="Start document processing workflow",
    description="Create a document record and start async Temporal workflow for OCR extraction, normalization, and entity resolution.",
    operation_id="start_document_workflow",
)
async def extract_ocr(
    request: OCRExtractionRequest,
    db_session: Annotated[AsyncSession, Depends(get_async_session)],
) -> dict:
    """Start async document processing workflow.

    This endpoint creates a document record and triggers the Temporal workflow
    for asynchronous processing. The workflow handles OCR extraction, normalization,
    classification, and entity resolution.

    Args:
        request: OCR extraction request containing the PDF URL
        db_session: Database session for document creation

    Returns:
        dict: Workflow start response with document_id and workflow_id

    Raises:
        HTTPException: If workflow start fails
    """
    pdf_url = str(request.pdf_url)

    LOGGER.info("Received workflow start request", extra={"pdf_url": pdf_url})

    try:
        # Create document repository
        document_repository = DocumentRepository(db_session)

        # TODO: Get user_id from auth / middleware
        DEFAULT_TEST_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
        
        # Create document record FIRST (before starting workflow)
        document = await document_repository.create_document(
            file_path=pdf_url,
            page_count=0,
            user_id=DEFAULT_TEST_USER_ID,
        )
        document_id = document.id
        
        # Commit document creation before starting workflow
        await db_session.commit()
        
        LOGGER.info(
            "Document created, starting workflow",
            extra={"document_id": str(document_id), "pdf_url": pdf_url}
        )
        
        # Get Temporal client
        temporal_client = await get_temporal_client()
        
        # Start ProcessDocumentWorkflow asynchronously
        workflow_handle = await temporal_client.start_workflow(
            ProcessDocumentWorkflow.run,
            str(document_id),  # Pass document_id as string
            id=f"process-doc-{document_id}",
            task_queue="documents-queue",
        )
        
        LOGGER.info(
            "Workflow started successfully",
            extra={
                "document_id": str(document_id),
                "workflow_id": workflow_handle.id,
                "pdf_url": pdf_url,
            }
        )
        
        # Return immediately with workflow ID
        return {
            "document_id": str(document_id),
            "workflow_id": workflow_handle.id,
            "status": "processing",
            "message": "Document processing started. Use workflow_id to check status.",
        }

    except Exception as e:
        LOGGER.error(
            "Failed to start workflow",
            exc_info=True,
            extra={"pdf_url": pdf_url, "error": str(e)},
        )
        
        # Rollback document creation if workflow start fails
        try:
            await db_session.rollback()
        except Exception:
            pass
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "WorkflowStartError",
                "message": "Failed to start document processing workflow",
                "detail": str(e),
            },
        ) from e


@router.get(
    "/status/{workflow_id}",
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "Workflow status retrieved successfully",
        },
        404: {
            "description": "Workflow not found",
            "model": ErrorResponse,
        },
        500: {
            "description": "Internal server error",
            "model": ErrorResponse,
        },
    },
    summary="Get workflow status",
    description="Query the current status and progress of a document processing workflow.",
    operation_id="get_workflow_status",
)
async def get_workflow_status(workflow_id: str) -> dict:
    """Get workflow execution status and progress.

    Args:
        workflow_id: Workflow execution ID returned from /extract endpoint

    Returns:
        dict: Workflow status with current phase and progress

    Raises:
        HTTPException: If workflow not found or query fails
    """
    LOGGER.info("Querying workflow status", extra={"workflow_id": workflow_id})

    try:
        # Get Temporal client
        temporal_client = await get_temporal_client()
        
        # Get workflow handle
        handle = temporal_client.get_workflow_handle(workflow_id)
        
        # Query workflow status
        status_data = await handle.query("get_status")
        
        LOGGER.info(
            "Workflow status retrieved",
            extra={
                "workflow_id": workflow_id,
                "status": status_data.get("status"),
                "progress": status_data.get("progress"),
            }
        )
        
        return {
            "workflow_id": workflow_id,
            "status": status_data.get("status", "unknown"),
            "current_phase": status_data.get("current_phase"),
            "progress": status_data.get("progress", 0.0),
        }

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
        ) from e

