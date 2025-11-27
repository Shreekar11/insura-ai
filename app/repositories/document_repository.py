from typing import Optional
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base_repository import BaseRepository
from app.database.models import Document
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class DocumentRepository(BaseRepository[Document]):
    """Repository for managing Document records.
    
    Inherits from BaseRepository for standard CRUD operations.
    """

    def __init__(self, session: AsyncSession):
        """Initialize document repository.
        
        Args:
            session: SQLAlchemy async session
        """
        super().__init__(session, Document)

    async def create_document(
        self,
        file_path: str,
        page_count: int,
        user_id: UUID,
        mime_type: str = "application/pdf",
        status: str = "ocr_processing"
    ) -> Document:
        """Create a new document record.
        
        Args:
            file_path: Path or URL of the document
            page_count: Number of pages
            user_id: ID of the user owning the document
            mime_type: MIME type of the document
            status: Initial status
            
        Returns:
            Created Document record
        """
        return await self.create(
            user_id=user_id,
            file_path=file_path,
            page_count=page_count,
            status=status,
            mime_type=mime_type,
            uploaded_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )

    async def update_status(self, document_id: UUID, status: str) -> bool:
        """Update document status.
        
        Args:
            document_id: Document ID
            status: New status string
            
        Returns:
            True if updated, False if not found
        """
        return await self.update(document_id, status=status) is not None
