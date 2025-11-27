"""OCR extraction API endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.request.ocr import OCRExtractionRequest
from app.models.response.ocr import OCRExtractionResponse, ErrorResponse
from app.config import settings
from app.database import get_async_session
from app.services.ocr.ocr_service import OCRService
from app.dependencies import get_ocr_service
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
    response_model=OCRExtractionResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "OCR extraction completed successfully",
            "model": OCRExtractionResponse,
        },
        400: {
            "description": "Invalid request or document",
            "model": ErrorResponse,
        },
        408: {
            "description": "OCR processing timeout",
            "model": ErrorResponse,
        },
        500: {
            "description": "Internal server error",
            "model": ErrorResponse,
        },
    },
    summary="Extract text from PDF document",
    description="Extract text content from a PDF document using OCR. Accepts a public URL to the PDF document.",
    operation_id="extract_pdf_text_with_mistral_ocr_service",
)
async def extract_ocr(
    request: OCRExtractionRequest,
    ocr_service: Annotated[OCRService, Depends(get_ocr_service)],
    db_session: Annotated[AsyncSession, Depends(get_async_session)],
) -> OCRExtractionResponse:
    """Extract text from a PDF document using OCR.

    This endpoint accepts a public URL to a PDF document and returns the extracted
    text content along with confidence scores and metadata.

    Args:
        request: OCR extraction request containing the PDF URL
        ocr_service: Injected OCR service instance
        db_session: Database session for committing changes

    Returns:
        OCRExtractionResponse: Extracted text and metadata

    Raises:
        HTTPException: If extraction fails or times out
    """
    pdf_url = str(request.pdf_url)

    LOGGER.info("Received OCR extraction request", extra={"pdf_url": pdf_url})

    try:
        # Extract text using service
        result = await ocr_service.extract_text_from_url(pdf_url)

        response = OCRExtractionResponse(
            document_id=result.document_id,
            status="Completed" if result.success else "Failed",
            metadata=result.metadata,
            layout=result.layout,
        )
        
        try:
            await db_session.commit()
            LOGGER.info("Database changes committed successfully")
        except Exception as commit_error:
            LOGGER.error(f"Failed to commit database changes: {commit_error}")
            await db_session.rollback()
        
        LOGGER.info(
            "OCR extraction completed successfully",
            extra={
                "pdf_url": pdf_url,
                "document_id": str(result.document_id) if result.document_id else None,
                "text_length": len(result.text),
                "classification": result.metadata.get("classification"),
            },
        )

        return response

    except InvalidDocumentError as e:
        LOGGER.error(
            "Invalid document error",
            exc_info=True,
            extra={"pdf_url": pdf_url, "error": str(e)},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "InvalidDocumentError",
                "message": "Invalid or inaccessible document",
                "detail": str(e),
            },
        ) from e

    except OCRTimeoutError as e:
        LOGGER.error(
            "OCR timeout error",
            exc_info=True,
            extra={"pdf_url": pdf_url, "error": str(e)},
        )
        raise HTTPException(
            status_code=status.HTTP_408_REQUEST_TIMEOUT,
            detail={
                "error": "OCRTimeoutError",
                "message": "OCR processing timed out",
                "detail": str(e),
            },
        ) from e

    except (OCRExtractionError, APIClientError) as e:
        LOGGER.error(
            "OCR extraction error",
            exc_info=True,
            extra={"pdf_url": pdf_url, "error": str(e)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": type(e).__name__,
                "message": "Failed to extract text from document",
                "detail": str(e),
            },
        ) from e

    except Exception as e:
        LOGGER.error(
            "Unexpected error during OCR extraction",
            exc_info=True,
            extra={"pdf_url": pdf_url, "error": str(e)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "InternalServerError",
                "message": "An unexpected error occurred",
                "detail": str(e),
            },
        ) from e

