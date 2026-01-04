"""Workflow orchestration API endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4

from app.models.request.ocr import OCRExtractionRequest
from app.models.response.ocr import ErrorResponse
from app.config import settings
from app.database import get_async_session
from app.repositories.document_repository import DocumentRepository
from app.repositories.workflow_repository import (
    WorkflowRepository,
    WorkflowDefinitionRepository,
    WorkflowDocumentRepository,
)
from app.temporal_client import get_temporal_client
from app.temporal.workflows.process_document import ProcessDocumentWorkflow
from app.database.models import Document, Workflow
from app.utils.exceptions import (
    OCRExtractionError,
    OCRTimeoutError,
    InvalidDocumentError,
    APIClientError,
)
from app.utils.logging import get_logger
import os
from docling.document_converter import DocumentConverter
from docling.chunking import HybridChunker

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

    Transaction Flow:
    1. Create document record
    2. Create workflow_document record (with null workflow_id)
    3. Get/create workflow definition
    4. Create workflow record (with workflow_document_id)
    5. Update workflow_document with workflow_id
    6. Commit transaction
    7. Start Temporal workflow
    8. Update temporal_workflow_id and commit

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
        # Create repositories
        document_repository = DocumentRepository(db_session)
        workflow_repository = WorkflowRepository(db_session)
        workflow_doc_repository = WorkflowDocumentRepository(db_session)
        definition_repository = WorkflowDefinitionRepository(db_session)

        # TODO: Get user_id from auth / middleware
        DEFAULT_TEST_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
        
        # ===== TRANSACTION START =====
        # All database operations before Temporal workflow start
        
        # Step 1: Create document record
        LOGGER.info("Creating document record", extra={"pdf_url": pdf_url})
        document = await document_repository.create_document(
            file_path=pdf_url,
            page_count=0,
            user_id=DEFAULT_TEST_USER_ID,
        )
        document_id = document.id
        LOGGER.info(
            "Document created",
            extra={"document_id": str(document_id), "pdf_url": pdf_url}
        )
        
        # Step 2: Create workflow_document record with NULL workflow_id
        LOGGER.info(
            "Creating workflow_document record",
            extra={"document_id": str(document_id)}
        )
        workflow_document = await workflow_doc_repository.create_workflow_document(
            document_id=document_id,
            workflow_id=None  # Initially null
        )
        workflow_document_id = workflow_document.id
        LOGGER.info(
            "WorkflowDocument created",
            extra={
                "workflow_document_id": str(workflow_document_id),
                "document_id": str(document_id)
            }
        )
        
        # Step 3: Get or create default workflow definition
        workflow_key = "document_extraction"
        LOGGER.info(
            "Getting workflow definition",
            extra={"workflow_key": workflow_key}
        )
        definition = await definition_repository.get_by_key(workflow_key)
        if not definition:
            LOGGER.info(
                "Creating new workflow definition",
                extra={"workflow_key": workflow_key}
            )
            definition = await definition_repository.create(
                workflow_key=workflow_key,
                display_name="Document Extraction",
                description="Standard document processing: OCR, Classification, Extraction, Enrichment",
                supports_multi_docs=False
            )
        
        # Step 4: Create workflow record with workflow_document_id
        LOGGER.info(
            "Creating workflow record",
            extra={
                "workflow_document_id": str(workflow_document_id),
                "definition_id": str(definition.id)
            }
        )
        workflow_record = await workflow_repository.create_workflow(
            workflow_document_id=workflow_document_id,
            workflow_definition_id=definition.id,
            status="running"
        )
        workflow_id = workflow_record.id
        LOGGER.info(
            "Workflow record created",
            extra={"workflow_id": str(workflow_id)}
        )
        
        # Step 5: Update workflow_document with workflow_id
        LOGGER.info(
            "Linking workflow to workflow_document",
            extra={
                "workflow_document_id": str(workflow_document_id),
                "workflow_id": str(workflow_id)
            }
        )
        await workflow_doc_repository.update_workflow_link(
            workflow_document_id=workflow_document_id,
            workflow_id=workflow_id
        )
        
        # Step 6: Commit all database changes before starting Temporal workflow
        await db_session.commit()
        LOGGER.info(
            "Database transaction committed",
            extra={
                "document_id": str(document_id),
                "workflow_id": str(workflow_id),
                "workflow_document_id": str(workflow_document_id)
            }
        )
        
        # ===== TRANSACTION END =====
        
        # Step 7: Start Temporal workflow (external system call)
        LOGGER.info(
            "Starting Temporal workflow",
            extra={
                "document_id": str(document_id),
                "workflow_id": str(workflow_id),
                "pdf_url": pdf_url
            }
        )
        
        # Get Temporal client
        temporal_client = await get_temporal_client()
        
        # Start ProcessDocumentWorkflow asynchronously
        # We pass the workflow_id as the Temporal workflow ID for better tracking
        workflow_handle = await temporal_client.start_workflow(
            ProcessDocumentWorkflow.run,
            str(document_id),
            id=f"workflow-{workflow_id}",
            task_queue="documents-queue",
        )

        # Step 8: Update workflow record with the actual Temporal workflow ID
        LOGGER.info(
            "Updating workflow with Temporal ID",
            extra={
                "workflow_id": str(workflow_id),
                "temporal_id": workflow_handle.id
            }
        )
        await workflow_repository.update_temporal_id(
            workflow_id=workflow_id,
            temporal_workflow_id=workflow_handle.id
        )
        await db_session.commit()
        
        LOGGER.info(
            "Workflow started successfully",
            extra={
                "document_id": str(document_id),
                "workflow_id": str(workflow_id),
                "workflow_document_id": str(workflow_document_id),
                "temporal_id": workflow_handle.id,
                "pdf_url": pdf_url,
            }
        )
        
        # Return immediately with our database workflow ID
        return {
            "document_id": str(document_id),
            "workflow_id": str(workflow_id),
            "workflow_document_id": str(workflow_document_id),
            "temporal_id": workflow_handle.id,
            "status": "processing",
            "message": "Document processing started.",
        }

    except Exception as e:
        LOGGER.error(
            "Failed to start workflow",
            exc_info=True,
            extra={"pdf_url": pdf_url, "error": str(e)},
        )
        
        # Rollback any pending database changes
        try:
            await db_session.rollback()
            LOGGER.info("Database transaction rolled back")
        except Exception as rollback_error:
            LOGGER.error(
                "Failed to rollback transaction",
                exc_info=True,
                extra={"error": str(rollback_error)}
            )
        
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
