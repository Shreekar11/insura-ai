"""Repository for citation data access."""

from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from app.database.models import Citation, DocumentPage
from app.repositories.base_repository import BaseRepository
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class CitationRepository(BaseRepository[Citation]):
    """Repository for Citation model.

    Provides data access methods for citation source mappings,
    including lookups by document, source type, and source ID.
    """

    def __init__(self, session: AsyncSession):
        """Initialize the citation repository.

        Args:
            session: SQLAlchemy async session
        """
        super().__init__(session, Citation)

    async def get_by_source(
        self,
        document_id: UUID,
        source_type: str,
        source_id: str
    ) -> Optional[Citation]:
        """Get citation by source reference.

        Args:
            document_id: Document UUID
            source_type: Type of extracted item (effective_coverage, etc.)
            source_id: Canonical ID or stable ID of the source item

        Returns:
            Citation if found, None otherwise
        """
        try:
            query = select(Citation).where(
                and_(
                    Citation.document_id == document_id,
                    Citation.source_type == source_type,
                    Citation.source_id == source_id
                )
            )
            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            LOGGER.error(
                f"Error getting citation by source: {e}",
                extra={
                    "document_id": str(document_id),
                    "source_type": source_type,
                    "source_id": source_id
                },
                exc_info=True
            )
            raise

    async def get_by_document(
        self,
        document_id: UUID,
        source_type: Optional[str] = None
    ) -> List[Citation]:
        """Get all citations for a document.

        Args:
            document_id: Document UUID
            source_type: Optional filter by source type

        Returns:
            List of citations for the document
        """
        try:
            query = select(Citation).where(Citation.document_id == document_id)
            if source_type:
                query = query.where(Citation.source_type == source_type)
            query = query.order_by(Citation.primary_page, Citation.created_at)

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            LOGGER.error(
                f"Error getting citations by document: {e}",
                extra={"document_id": str(document_id)},
                exc_info=True
            )
            raise

    async def get_by_page(
        self,
        document_id: UUID,
        page_number: int
    ) -> List[Citation]:
        """Get all citations that appear on a specific page.

        Args:
            document_id: Document UUID
            page_number: 1-indexed page number

        Returns:
            List of citations on the specified page
        """
        try:
            query = select(Citation).where(
                and_(
                    Citation.document_id == document_id,
                    Citation.primary_page == page_number
                )
            )
            result = await self.session.execute(query)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            LOGGER.error(
                f"Error getting citations by page: {e}",
                extra={
                    "document_id": str(document_id),
                    "page_number": page_number
                },
                exc_info=True
            )
            raise

    async def bulk_create(self, citations: List[dict]) -> List[Citation]:
        """Bulk create citations.

        Args:
            citations: List of citation dictionaries

        Returns:
            List of created Citation objects
        """
        try:
            objects = [Citation(**c) for c in citations]
            self.session.add_all(objects)
            await self.session.flush()

            LOGGER.info(
                f"Bulk created {len(objects)} citations",
                extra={"count": len(objects)}
            )
            return objects
        except SQLAlchemyError as e:
            LOGGER.error(
                f"Error bulk creating citations: {e}",
                extra={"count": len(citations)},
                exc_info=True
            )
            raise

    async def upsert(
        self,
        document_id: UUID,
        source_type: str,
        source_id: str,
        **kwargs
    ) -> Citation:
        """Create or update a citation.

        If a citation with the same (document_id, source_type, source_id)
        exists, update it. Otherwise, create a new one.

        Args:
            document_id: Document UUID
            source_type: Type of extracted item
            source_id: Canonical ID of the source item
            **kwargs: Additional fields to set

        Returns:
            The created or updated Citation
        """
        try:
            existing = await self.get_by_source(document_id, source_type, source_id)

            if existing:
                # Update existing citation
                for key, value in kwargs.items():
                    if hasattr(existing, key):
                        setattr(existing, key, value)
                await self.session.flush()
                return existing
            else:
                # Create new citation
                return await self.create(
                    document_id=document_id,
                    source_type=source_type,
                    source_id=source_id,
                    **kwargs
                )
        except SQLAlchemyError as e:
            LOGGER.error(
                f"Error upserting citation: {e}",
                extra={
                    "document_id": str(document_id),
                    "source_type": source_type,
                    "source_id": source_id
                },
                exc_info=True
            )
            raise

    async def delete_by_document(self, document_id: UUID) -> int:
        """Delete all citations for a document.

        Args:
            document_id: Document UUID

        Returns:
            Number of citations deleted
        """
        try:
            citations = await self.get_by_document(document_id)
            count = len(citations)

            for citation in citations:
                await self.session.delete(citation)

            await self.session.flush()

            LOGGER.info(
                f"Deleted {count} citations for document",
                extra={"document_id": str(document_id), "count": count}
            )
            return count
        except SQLAlchemyError as e:
            LOGGER.error(
                f"Error deleting citations by document: {e}",
                extra={"document_id": str(document_id)},
                exc_info=True
            )
            raise


class PageDimensionsRepository:
    """Repository for page dimension queries.

    Provides access to page dimensions stored in DocumentPage
    for coordinate transformation.
    """

    def __init__(self, session: AsyncSession):
        """Initialize the repository.

        Args:
            session: SQLAlchemy async session
        """
        self.session = session

    async def get_page_dimensions(
        self,
        document_id: UUID,
        page_number: int
    ) -> Optional[DocumentPage]:
        """Get dimensions for a specific page.

        Args:
            document_id: Document UUID
            page_number: 1-indexed page number

        Returns:
            DocumentPage with dimensions, or None if not found
        """
        try:
            query = select(DocumentPage).where(
                and_(
                    DocumentPage.document_id == document_id,
                    DocumentPage.page_number == page_number
                )
            )
            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            LOGGER.error(
                f"Error getting page dimensions: {e}",
                extra={
                    "document_id": str(document_id),
                    "page_number": page_number
                },
                exc_info=True
            )
            raise

    async def get_all_page_dimensions(
        self,
        document_id: UUID
    ) -> List[DocumentPage]:
        """Get dimensions for all pages in a document.

        Args:
            document_id: Document UUID

        Returns:
            List of DocumentPage objects with dimensions
        """
        try:
            query = (
                select(DocumentPage)
                .where(DocumentPage.document_id == document_id)
                .order_by(DocumentPage.page_number)
            )
            result = await self.session.execute(query)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            LOGGER.error(
                f"Error getting all page dimensions: {e}",
                extra={"document_id": str(document_id)},
                exc_info=True
            )
            raise


__all__ = [
    "CitationRepository",
    "PageDimensionsRepository",
]
