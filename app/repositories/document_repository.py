from typing import Optional, List
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.base_repository import BaseRepository
from app.database.models import Document, DocumentPage, PageManifestRecord
from app.models.page_data import PageData
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

    async def store_pages(
        self,
        document_id: UUID,
        pages: List[PageData]
    ) -> None:
        """Store OCR pages for a document.
        
        Args:
            document_id: Document ID
            pages: List of PageData objects from OCR extraction
        """
        LOGGER.info(f"Storing {len(pages)} pages for document {document_id}")
        
        # Delete existing pages for this document (if re-processing)
        await self.session.execute(
            select(DocumentPage).where(DocumentPage.document_id == document_id)
        )
        existing_pages = (await self.session.execute(
            select(DocumentPage).where(DocumentPage.document_id == document_id)
        )).scalars().all()
        
        for page in existing_pages:
            await self.session.delete(page)
        
        # Create new page records
        for page_data in pages:
            page = DocumentPage(
                document_id=document_id,
                page_number=page_data.page_number,
                text=page_data.text,
                markdown=page_data.markdown,
                additional_metadata=page_data.metadata or {},
            )
            self.session.add(page)
        
        await self.session.flush()
        LOGGER.info(f"Successfully stored {len(pages)} pages for document {document_id}")

    async def get_pages_by_document(
        self,
        document_id: UUID
    ) -> List[PageData]:
        """Fetch OCR pages for a document.
        
        Args:
            document_id: Document ID
            
        Returns:
            List of PageData objects
        """
        LOGGER.info(f"Fetching pages for document {document_id}")
        
        result = await self.session.execute(
            select(DocumentPage)
            .where(DocumentPage.document_id == document_id)
            .order_by(DocumentPage.page_number)
        )
        pages = result.scalars().all()
        
        if not pages:
            LOGGER.warning(f"No pages found for document {document_id}")
            return []
        
        # Convert to PageData objects
        page_data_list = [
            PageData(
                page_number=page.page_number,
                text=page.text or "",
                markdown=page.markdown or "",
                metadata=page.additional_metadata or {},
            )
            for page in pages
        ]
        
        LOGGER.info(f"Retrieved {len(page_data_list)} pages for document {document_id}")
        return page_data_list

    async def get_manifest_pages(
        self,
        document_id: UUID
    ) -> Optional[List[int]]:
        """Get pages_to_process from the page manifest for a document.
        
        Args:
            document_id: Document ID
            
        Returns:
            List of page numbers to process, or None if no manifest exists
        """
        LOGGER.info(f"Fetching manifest pages for document {document_id}")
        
        result = await self.session.execute(
            select(PageManifestRecord)
            .where(PageManifestRecord.document_id == document_id)
        )
        manifest = result.scalar_one_or_none()
        
        if not manifest:
            LOGGER.info(f"No manifest found for document {document_id}")
            return None
        
        pages_to_process = manifest.pages_to_process
        LOGGER.info(
            f"Found manifest with {len(pages_to_process)} pages to process",
            extra={
                "document_id": str(document_id),
                "pages_to_process": pages_to_process
            }
        )
        
        return pages_to_process
