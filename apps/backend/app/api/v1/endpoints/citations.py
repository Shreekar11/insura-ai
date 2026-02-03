"""Citation API endpoints for source mapping retrieval.

Provides endpoints for retrieving citation data that maps extracted
items (coverages, exclusions, etc.) to their source PDF locations.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Annotated, Optional

from app.core.database import get_async_session as get_session
from app.core.auth import get_current_user
from app.schemas.auth import CurrentUser
from app.schemas.citation import (
    CitationResponse,
    CitationListResponse,
    PageDimensionsResponse,
    DocumentPagesResponse,
)
from app.services.citation.citation_service import CitationService
from app.utils.logging import get_logger
from app.utils.responses import create_api_response

LOGGER = get_logger(__name__)

router = APIRouter()


async def get_citation_service(
    db_session: Annotated[AsyncSession, Depends(get_session)]
) -> CitationService:
    """Dependency for citation service."""
    return CitationService(db_session)


@router.get(
    "/documents/{document_id}/citations/{source_type}/{source_id}",
    response_model=dict,
    summary="Get citation for an extracted item",
    operation_id="get_citation",
)
async def get_citation(
    request: Request,
    document_id: UUID,
    source_type: str,
    source_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    citation_service: Annotated[CitationService, Depends(get_citation_service)],
) -> dict:
    """Get citation data for a specific extracted item.

    This endpoint retrieves the source mapping for an extracted item,
    including bounding box coordinates and verbatim text.

    Args:
        document_id: Document UUID
        source_type: Type of source (effective_coverage, effective_exclusion, etc.)
        source_id: Canonical ID or stable ID of the source item

    Returns:
        Citation with bounding boxes and verbatim text

    Raises:
        HTTPException 404: Citation not found
    """
    citation = await citation_service.get_citation(
        document_id, source_type, source_id
    )

    if not citation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Citation not found for {source_type}/{source_id}"
        )

    return create_api_response(
        data=citation.model_dump(),
        message="Citation retrieved successfully",
        request=request
    )


@router.get(
    "/documents/{document_id}/citations",
    response_model=dict,
    summary="Get all citations for a document",
    operation_id="list_citations",
)
async def list_citations(
    request: Request,
    document_id: UUID,
    source_type: Optional[str] = Query(
        None, description="Filter by source type (effective_coverage, effective_exclusion, etc.)"
    ),
    current_user: Annotated[CurrentUser, Depends(get_current_user)] = None,
    citation_service: Annotated[CitationService, Depends(get_citation_service)] = None,
) -> dict:
    """List all citations for a document.

    Returns all citations mapped to extracted items in the document.
    Optionally filter by source type.

    Args:
        document_id: Document UUID
        source_type: Optional filter by source type

    Returns:
        List of citations
    """
    result = await citation_service.list_citations(document_id, source_type)

    return create_api_response(
        data=result.model_dump(),
        message=f"Retrieved {result.total} citations",
        request=request
    )


@router.get(
    "/documents/{document_id}/pages/{page_number}/dimensions",
    response_model=dict,
    summary="Get page dimensions for coordinate transformation",
    operation_id="get_page_dimensions",
)
async def get_page_dimensions(
    request: Request,
    document_id: UUID,
    page_number: int,
    current_user: Annotated[CurrentUser, Depends(get_current_user)] = None,
    citation_service: Annotated[CitationService, Depends(get_citation_service)] = None,
) -> dict:
    """Get page dimensions for converting PDF coordinates to viewer coordinates.

    Returns page width, height (in PDF points), and rotation for
    accurate coordinate transformation on the frontend.

    Args:
        document_id: Document UUID
        page_number: 1-indexed page number

    Returns:
        Page dimensions

    Raises:
        HTTPException 404: Page not found
    """
    result = await citation_service.get_page_dimensions(document_id, page_number)

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Page {page_number} not found for document {document_id}"
        )

    return create_api_response(
        data=result.model_dump(),
        message="Page dimensions retrieved successfully",
        request=request
    )


@router.get(
    "/documents/{document_id}/pages/dimensions",
    response_model=dict,
    summary="Get all page dimensions for a document",
    operation_id="get_all_page_dimensions",
)
async def get_all_page_dimensions(
    request: Request,
    document_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)] = None,
    citation_service: Annotated[CitationService, Depends(get_citation_service)] = None,
) -> dict:
    """Get dimensions for all pages in a document.

    Returns page dimensions for all pages, useful for preloading
    coordinate transformation data.

    Args:
        document_id: Document UUID

    Returns:
        All page dimensions
    """
    result = await citation_service.get_all_page_dimensions(document_id)

    return create_api_response(
        data=result.model_dump(),
        message=f"Retrieved dimensions for {result.total_pages} pages",
        request=request
    )


@router.get(
    "/citations/{citation_id}",
    response_model=dict,
    summary="Get citation by ID",
    operation_id="get_citation_by_id",
)
async def get_citation_by_id(
    request: Request,
    citation_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)] = None,
    citation_service: Annotated[CitationService, Depends(get_citation_service)] = None,
) -> dict:
    """Get a citation by its ID.

    Args:
        citation_id: Citation UUID

    Returns:
        Citation data

    Raises:
        HTTPException 404: Citation not found
    """
    citation = await citation_service.get_citation_by_id(citation_id)

    if not citation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Citation {citation_id} not found"
        )

    return create_api_response(
        data=citation.model_dump(),
        message="Citation retrieved successfully",
        request=request
    )


__all__ = ["router"]
