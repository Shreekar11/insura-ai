"""Workflow routes with proper error handling and service integration."""

from typing import Annotated, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.services.workflow_service import WorkflowService
from app.core.exceptions import ValidationError, AppError
from app.utils.logging import get_logger
from app.core.auth import get_current_user
from app.schemas.auth import CurrentUser
from app.services.user_service import UserService
from app.core.dependencies import get_user_service
from app.services.storage_service import StorageService

from app.schemas.workflows.request import WorkflowExtractionRequest
from app.schemas.workflows.response import (
    WorkflowExtractionResponse,
    WorkflowStatusResponse,
    ErrorResponse
)

LOGGER = get_logger(__name__)

router = APIRouter()


async def get_workflow_service(
    db_session: Annotated[AsyncSession, Depends(get_async_session)]
) -> WorkflowService:
    """Dependency to create WorkflowService instance.

    This ensures consistent service instantiation across all routes.
    """
    return WorkflowService(db_session)


async def get_current_user_id(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    user_service: Annotated[UserService, Depends(get_user_service)],
) -> UUID:
    """Dependency to get current authenticated user ID.

    Ensures the user exists in our database and returns their internal ID.
    """
    # Ensure user exists in database (creates if needed)
    user = await user_service.ensure_user_exists(current_user)
    return user.id


async def get_storage_service() -> StorageService:
    """Dependency to create StorageService instance."""
    return StorageService()


@router.post(
    "/extract",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=WorkflowExtractionResponse,
    responses={
        202: {
            "description": "Workflow started successfully",
            "model": WorkflowExtractionResponse
        },
        400: {
            "description": "Invalid request parameters",
            "model": ErrorResponse
        },
        500: {
            "description": "Internal server error",
            "model": ErrorResponse
        }
    },
    summary="Start document processing workflow",
    description=(
        "Initiates an asynchronous document processing workflow that includes:\n"
        "- Document record creation\n"
        "- OCR text extraction\n"
        "- Document classification\n"
        "- Section and entity field extraction\n"
        "- Entity resolution and extraction\n"
        "- Document summarization\n\n"
        "Returns workflow and document IDs for status tracking."
    ),
    operation_id="start_document_extraction_workflow",
)
async def start_document_extraction(
    workflow_service: Annotated[WorkflowService, Depends(get_workflow_service)],
    storage_service: Annotated[StorageService, Depends(get_storage_service)],
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    request: Optional[WorkflowExtractionRequest] = None,
    file: Optional[UploadFile] = File(None),
) -> WorkflowExtractionResponse:
    """Start async document extraction workflow.
    
    This endpoint uses the BaseService pattern with execute() for:
    - Automatic input validation
    - Standardized error handling
    - Consistent logging
    - Transaction management
    
    Args:
        request: Workflow extraction request with PDF URL
        workflow_service: Injected workflow service instance
        user_id: Current authenticated user ID
        
    Returns:
        WorkflowExtractionResponse with workflow details
        
    Raises:
        HTTPException: On validation or execution errors
    """
    try:
        pdf_url = None
        
        # 1. Handle file upload if provided
        if file:
            LOGGER.info(f"Uploading file {file.filename} to Supabase storage")
            # Generate a unique path for the file
            import uuid
            file_extension = file.filename.split(".")[-1] if "." in file.filename else "pdf"
            storage_path = f"{user_id}/{uuid.uuid4()}.{file_extension}"
            
            # Upload to 'documents' bucket as requested
            await storage_service.upload_file(file, bucket="documents", path=storage_path)
            
            # Get signed URL
            pdf_url = await storage_service.get_signed_url(bucket="documents", path=storage_path)
            LOGGER.info(f"File uploaded successfully, signed URL generated: {pdf_url}")
        
        # 2. Use pdf_url from request if no file provided
        elif request and request.pdf_url:
            pdf_url = str(request.pdf_url)
        
        if not pdf_url:
            raise ValidationError("Either a file upload or a pdf_url in the request is required")

        # Use BaseService.execute() pattern for standardized flow
        result = await workflow_service.execute_start_extraction(
            pdf_url=pdf_url,
            user_id=user_id
        )
        
        LOGGER.info(
            "Document extraction workflow started successfully",
            extra={
                "workflow_id": result["workflow_id"],
                "temporal_id": result["temporal_id"],
                "user_id": str(user_id)
            }
        )
        
        return WorkflowExtractionResponse(**result)
        
    except ValidationError as e:
        # Handle validation errors with 400 Bad Request
        LOGGER.warning(
            "Workflow validation failed",
            extra={
                "pdf_url": str(request.pdf_url),
                "user_id": str(user_id),
                "error": str(e)
            }
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "ValidationError",
                "message": "Invalid request parameters",
                "detail": str(e),
            },
        )
        
    except AppError as e:
        # Handle application-level errors with 500 Internal Server Error
        LOGGER.error(
            "Failed to start document extraction workflow",
            exc_info=True,
            extra={
                "pdf_url": str(request.pdf_url),
                "user_id": str(user_id),
                "error": str(e)
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "WorkflowStartError",
                "message": "Failed to start document extraction workflow",
                "detail": str(e),
            },
        )
        
    except Exception as e:
        # Catch-all for unexpected errors
        LOGGER.error(
            "Unexpected error starting workflow",
            exc_info=True,
            extra={
                "pdf_url": str(request.pdf_url),
                "user_id": str(user_id),
                "error": str(e)
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "InternalError",
                "message": "An unexpected error occurred",
                "detail": "Please contact support if this persists",
            },
        )


@router.get(
    "/status/{workflow_id}",
    status_code=status.HTTP_200_OK,
    response_model=WorkflowStatusResponse,
    responses={
        200: {
            "description": "Workflow status retrieved successfully",
            "model": WorkflowStatusResponse
        },
        400: {
            "description": "Invalid workflow ID",
            "model": ErrorResponse
        },
        404: {
            "description": "Workflow not found",
            "model": ErrorResponse
        },
        500: {
            "description": "Internal server error",
            "model": ErrorResponse
        }
    },
    summary="Get workflow status",
    description=(
        "Query the current status and progress of a document processing workflow.\n\n"
        "Returns information about:\n"
        "- Current workflow status (running, completed, failed)\n"
        "- Current processing phase\n"
        "- Overall progress percentage\n\n"
        "Use this endpoint to poll for workflow completion or monitor progress."
    ),
    operation_id="get_workflow_execution_status",
)
async def get_workflow_status(
    workflow_id: str,
    workflow_service: Annotated[WorkflowService, Depends(get_workflow_service)]
) -> WorkflowStatusResponse:
    """Get workflow execution status and progress.
    
    Uses BaseService.execute() pattern for standardized error handling.
    
    Args:
        workflow_id: Temporal workflow execution ID
        workflow_service: Injected workflow service instance
        
    Returns:
        WorkflowStatusResponse with current status
        
    Raises:
        HTTPException: On validation or query errors
    """
    try:
        # Use BaseService.execute() pattern
        result = await workflow_service.execute_get_status(workflow_id)
        
        LOGGER.info(
            "Workflow status retrieved successfully",
            extra={
                "workflow_id": workflow_id,
                "status": result.get("status")
            }
        )
        
        return WorkflowStatusResponse(**result)
        
    except ValidationError as e:
        # Handle validation errors (invalid workflow_id format)
        LOGGER.warning(
            "Invalid workflow ID format",
            extra={"workflow_id": workflow_id, "error": str(e)}
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "ValidationError",
                "message": "Invalid workflow ID",
                "detail": str(e),
            },
        )
        
    except AppError as e:
        # Check if it's a "not found" error
        if "not found" in str(e).lower():
            LOGGER.warning(
                "Workflow not found",
                extra={"workflow_id": workflow_id}
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "WorkflowNotFound",
                    "message": f"Workflow {workflow_id} not found",
                    "detail": str(e),
                },
            )
        
        # Other application errors
        LOGGER.error(
            "Failed to query workflow status",
            exc_info=True,
            extra={"workflow_id": workflow_id, "error": str(e)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "WorkflowQueryError",
                "message": "Failed to query workflow status",
                "detail": str(e),
            },
        )
        
    except Exception as e:
        # Catch-all for unexpected errors
        LOGGER.error(
            "Unexpected error querying workflow status",
            exc_info=True,
            extra={"workflow_id": workflow_id, "error": str(e)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "InternalError",
                "message": "An unexpected error occurred",
                "detail": "Please contact support if this persists",
            },
        )


@router.get(
    "/stages",
    status_code=status.HTTP_200_OK,
    response_model=List[dict],
    responses={
        200: {
            "description": "Document stages retrieved successfully"
        },
        400: {
            "description": "Invalid document ID or workflow ID",
            "model": ErrorResponse
        },
        404: {
            "description": "Document not found",
            "model": ErrorResponse
        },
        500: {
            "description": "Internal server error",
            "model": ErrorResponse
        }
    },
    summary="Get document processing stages",
    description=(
        "Retrieve the completion status of all processing stages for a specific document.\n\n"
        "Optionally filter by workflow ID to see stages for a specific workflow execution."
    ),
    operation_id="get_document_processing_stages",
)
async def get_document_stages(
    document_id: UUID,
    workflow_service: Annotated[WorkflowService, Depends(get_workflow_service)],
    workflow_id: UUID,
) -> List[dict]:
    """Get completion status of all processing stages for a document.
    
    Note: This method doesn't use the BaseService.execute() pattern because
    FastAPI already validates the UUID format, and the method is simple enough.
    
    For more complex validation needs, consider wrapping this in execute().
    
    Args:
        document_id: Document UUID to query
        workflow_service: Injected workflow service instance
        workflow_id: Workflow UUID to query
        
    Returns:
        List of stage records for the document
        
    Raises:
        HTTPException: On query errors or if document not found
    """
    try:
        result = await workflow_service.get_document_stage(document_id, workflow_id)
        
        # Check if document exists (empty result might mean not found)
        if not result:
            LOGGER.warning(
                "No stages found for document",
                extra={
                    "document_id": str(document_id),
                    "workflow_id": str(workflow_id) if workflow_id else None
                }
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "DocumentNotFound",
                    "message": f"No stages found for document {document_id}",
                    "detail": "Document may not exist or has not started processing",
                }
            )
        
        LOGGER.info(
            "Retrieved document stages",
            extra={
                "document_id": str(document_id),
                "workflow_id": str(workflow_id) if workflow_id else None,
                "stage_count": len(result)
            }
        )
        
        return result
        
    except HTTPException:
        # Re-raise HTTPExceptions as-is
        raise
        
    except AppError as e:
        LOGGER.error(
            "Failed to get document stages",
            exc_info=True,
            extra={
                "document_id": str(document_id),
                "workflow_id": str(workflow_id) if workflow_id else None,
                "error": str(e)
            }
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "StageQueryError",
                "message": "Failed to retrieve document stages",
                "detail": str(e),
            }
        )
        
    except Exception as e:
        LOGGER.error(
            "Unexpected error getting document stages",
            exc_info=True,
            extra={
                "document_id": str(document_id),
                "workflow_id": str(workflow_id) if workflow_id else None,
                "error": str(e)
            }
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "InternalError",
                "message": "An unexpected error occurred",
                "detail": "Please contact support if this persists",
            }
        )
