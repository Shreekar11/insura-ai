"""Citation service for managing source mapping and retrieval.

This service provides the business logic for creating, retrieving,
and managing citations that map extracted items back to their
source locations in PDF documents.
"""

from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Citation
from app.repositories.citation_repository import (
    CitationRepository,
    PageDimensionsRepository,
)
from app.schemas.citation import (
    BoundingBox,
    CitationCreate,
    CitationResponse,
    CitationSpan,
    CitationListResponse,
    PageDimensions,
    PageDimensionsResponse,
    DocumentPagesResponse,
    SourceType,
)
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class CitationService:
    """Service for citation management.

    Provides methods for creating, retrieving, and managing citations
    that map extracted policy items to their source PDF locations.
    """

    def __init__(self, session: AsyncSession):
        """Initialize the citation service.

        Args:
            session: SQLAlchemy async session
        """
        self.session = session
        self.citation_repo = CitationRepository(session)
        self.page_dims_repo = PageDimensionsRepository(session)

    async def create_citation(
        self,
        citation_data: CitationCreate
    ) -> CitationResponse:
        """Create a new citation.

        Args:
            citation_data: Citation creation data

        Returns:
            Created citation response
        """
        LOGGER.debug(
            "[CITATION-SVC] create_citation called",
            extra={
                "document_id": str(citation_data.document_id),
                "source_type": citation_data.source_type.value,
                "source_id": citation_data.source_id,
                "primary_page": citation_data.primary_page,
                "span_count": len(citation_data.spans),
                "verbatim_text_length": len(citation_data.verbatim_text) if citation_data.verbatim_text else 0,
            }
        )

        # Convert spans to JSON-serializable format
        spans_json = [
            {
                "page_number": span.page_number,
                "bounding_boxes": [
                    {"x0": bb.x0, "y0": bb.y0, "x1": bb.x1, "y1": bb.y1}
                    for bb in span.bounding_boxes
                ],
                "text_content": span.text_content
            }
            for span in citation_data.spans
        ]

        # Convert page_range to dict if present
        page_range_dict = None
        if citation_data.page_range:
            page_range_dict = {
                "start": citation_data.page_range.start,
                "end": citation_data.page_range.end
            }

        LOGGER.debug(
            "[CITATION-SVC] Calling citation_repo.create",
            extra={
                "spans_json_length": len(spans_json),
                "has_page_range": page_range_dict is not None,
            }
        )

        try:
            # Use upsert to handle duplicate (document_id, source_type, source_id)
            # gracefully - updates existing citation instead of throwing error
            citation = await self.citation_repo.upsert(
                document_id=citation_data.document_id,
                source_type=citation_data.source_type.value,
                source_id=citation_data.source_id,
                spans=spans_json,
                verbatim_text=citation_data.verbatim_text,
                primary_page=citation_data.primary_page,
                page_range=page_range_dict,
                extraction_confidence=citation_data.extraction_confidence,
                extraction_method=citation_data.extraction_method.value,
                clause_reference=citation_data.clause_reference,
            )

            LOGGER.info(
                "[CITATION-SVC] ✓ Citation persisted to database",
                extra={
                    "citation_id": str(citation.id),
                    "document_id": str(citation_data.document_id),
                    "source_type": citation_data.source_type.value,
                    "source_id": citation_data.source_id,
                    "primary_page": citation_data.primary_page,
                }
            )

            return self._to_response(citation)

        except Exception as e:
            LOGGER.error(
                "[CITATION-SVC] ✗ Failed to persist citation",
                extra={
                    "document_id": str(citation_data.document_id),
                    "source_type": citation_data.source_type.value,
                    "source_id": citation_data.source_id,
                    "error": str(e),
                },
                exc_info=True
            )
            raise

    async def get_citation(
        self,
        document_id: UUID,
        source_type: str,
        source_id: str
    ) -> Optional[CitationResponse]:
        """Get citation by source reference.

        Args:
            document_id: Document UUID
            source_type: Type of extracted item
            source_id: Canonical ID of the source item

        Returns:
            Citation response if found, None otherwise
        """
        citation = await self.citation_repo.get_by_source(
            document_id, source_type, source_id
        )

        if not citation:
            return None

        return self._to_response(citation)

    async def get_citation_by_id(
        self,
        citation_id: UUID
    ) -> Optional[CitationResponse]:
        """Get citation by its ID.

        Args:
            citation_id: Citation UUID

        Returns:
            Citation response if found, None otherwise
        """
        citation = await self.citation_repo.get_by_id(citation_id)

        if not citation:
            return None

        return self._to_response(citation)

    async def list_citations(
        self,
        document_id: UUID,
        source_type: Optional[str] = None
    ) -> CitationListResponse:
        """List all citations for a document.

        Args:
            document_id: Document UUID
            source_type: Optional filter by source type

        Returns:
            List of citations
        """
        LOGGER.info(
            "[CITATION-SVC] list_citations called",
            extra={
                "document_id": str(document_id),
                "source_type_filter": source_type,
            }
        )

        citations = await self.citation_repo.get_by_document(
            document_id, source_type
        )

        LOGGER.info(
            "[CITATION-SVC] Retrieved citations from database",
            extra={
                "document_id": str(document_id),
                "citation_count": len(citations),
                "source_types": list(set(c.source_type for c in citations)) if citations else [],
            }
        )

        return CitationListResponse(
            document_id=document_id,
            citations=[self._to_response(c) for c in citations],
            total=len(citations)
        )

    async def get_page_dimensions(
        self,
        document_id: UUID,
        page_number: int
    ) -> Optional[PageDimensionsResponse]:
        """Get page dimensions for coordinate transformation.

        Args:
            document_id: Document UUID
            page_number: 1-indexed page number

        Returns:
            Page dimensions if found
        """
        page = await self.page_dims_repo.get_page_dimensions(
            document_id, page_number
        )

        if not page:
            return None

        return PageDimensionsResponse(
            document_id=document_id,
            page_number=page_number,
            width_points=float(page.width_points) if page.width_points else 0.0,
            height_points=float(page.height_points) if page.height_points else 0.0,
            rotation=page.rotation or 0
        )

    async def get_all_page_dimensions(
        self,
        document_id: UUID
    ) -> DocumentPagesResponse:
        """Get dimensions for all pages in a document.

        Args:
            document_id: Document UUID

        Returns:
            All page dimensions
        """
        pages = await self.page_dims_repo.get_all_page_dimensions(document_id)

        return DocumentPagesResponse(
            document_id=document_id,
            pages=[
                PageDimensions(
                    page_number=p.page_number,
                    width_points=float(p.width_points) if p.width_points else 0.0,
                    height_points=float(p.height_points) if p.height_points else 0.0,
                    rotation=p.rotation or 0
                )
                for p in pages
            ],
            total_pages=len(pages)
        )

    async def delete_citation(self, citation_id: UUID) -> bool:
        """Delete a citation.

        Args:
            citation_id: Citation UUID

        Returns:
            True if deleted, False if not found
        """
        return await self.citation_repo.delete(citation_id)

    async def delete_document_citations(self, document_id: UUID) -> int:
        """Delete all citations for a document.

        Args:
            document_id: Document UUID

        Returns:
            Number of citations deleted
        """
        return await self.citation_repo.delete_by_document(document_id)

    def _to_response(self, citation: Citation) -> CitationResponse:
        """Convert Citation model to response schema.

        Args:
            citation: Citation database model

        Returns:
            CitationResponse schema
        """
        # Parse spans from JSON
        spans = [
            CitationSpan(
                page_number=s["page_number"],
                bounding_boxes=[
                    BoundingBox(**bb) for bb in s["bounding_boxes"]
                ],
                text_content=s["text_content"]
            )
            for s in citation.spans
        ]

        return CitationResponse(
            id=citation.id,
            document_id=citation.document_id,
            source_type=citation.source_type,
            source_id=citation.source_id,
            spans=spans,
            verbatim_text=citation.verbatim_text,
            primary_page=citation.primary_page,
            page_range=citation.page_range,
            extraction_confidence=(
                float(citation.extraction_confidence)
                if citation.extraction_confidence else None
            ),
            extraction_method=citation.extraction_method,
            clause_reference=citation.clause_reference,
            created_at=citation.created_at
        )


__all__ = [
    "CitationService",
]
