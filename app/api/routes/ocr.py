"""OCR extraction API endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.models.request.ocr import OCRExtractionRequest
from app.models.response.ocr import OCRExtractionResponse, ErrorResponse
from app.config import settings
from app.services.ocr_service import OCRService
from app.utils.exceptions import (
    OCRExtractionError,
    OCRTimeoutError,
    InvalidDocumentError,
    APIClientError,
)
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)

router = APIRouter()


def get_ocr_service() -> OCRService:
    """Provide a configured OCR service instance.

    Returns:
        OCRService: Configured OCR service instance
    """
    return OCRService(
        api_key=settings.mistral_api_key,
        api_url=settings.mistral_api_url,
        model=settings.mistral_model,
        timeout=settings.ocr_timeout,
        max_retries=settings.max_retries,
        retry_delay=settings.retry_delay,
    )


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
) -> OCRExtractionResponse:
    """Extract text from a PDF document using OCR.

    This endpoint accepts a public URL to a PDF document and returns the extracted
    text content along with confidence scores and metadata.

    Args:
        request: OCR extraction request containing the PDF URL
        ocr_service: Injected OCR service instance

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

        # Build response
        response = OCRExtractionResponse(
            text=result.text,
            confidence=result.confidence,
            status="Completed",
            metadata=result.metadata,
            layout=result.layout,
        )

        LOGGER.info(
            "OCR extraction completed successfully",
            extra={
                "pdf_url": pdf_url,
                "document_id": str(response.document_id),
                "text_length": len(result.text),
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

