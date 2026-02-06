from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.repositories.base_repository import BaseRepository
from app.database.models import Document, DocumentPage, PageManifestRecord
from app.models.page_data import PageData
from app.utils.logging import get_logger
from app.services.processed.services.ocr.coordinate_extraction_service import (
    WordCoordinate,
    PageMetadata,
)

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
        document_name: Optional[str] = None,
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
            document_name=document_name,
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
                # Store page dimensions for citation coordinate transformation
                width_points=page_data.width_points,
                height_points=page_data.height_points,
                rotation=page_data.rotation or 0,
            )
            self.session.add(page)
        
        await self.session.flush()
        LOGGER.info(f"Successfully stored {len(pages)} pages for document {document_id}")

    async def get_pages_by_document(
        self,
        document_id: UUID
    ) -> List[PageData]:
        """Fetch OCR pages for a document."""
        return await self.get_pages(document_id)

    async def get_pages(
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

    async def update_page_metadata_bulk(
        self,
        document_id: UUID,
        page_section_map: dict[int, str]
    ) -> None:
        """Update metadata for multiple pages in a document.
        
        Args:
            document_id: Document ID
            page_section_map: Mapping of page number to section type
        """
        LOGGER.info(f"Updating metadata for {len(page_section_map)} pages of document {document_id}")
        
        result = await self.session.execute(
            select(DocumentPage)
            .where(DocumentPage.document_id == document_id)
        )
        pages = result.scalars().all()
        
        for page in pages:
            if page.page_number in page_section_map:
                if page.additional_metadata is None:
                    page.additional_metadata = {}
                page.additional_metadata["page_type"] = page_section_map[page.page_number]
                page.additional_metadata["section_from_manifest"] = True
                
        await self.session.flush()
        LOGGER.info(f"Updated metadata for {len(page_section_map)} pages")

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

    async def get_word_coordinates_for_citation(
        self,
        document_id: UUID
    ) -> Tuple[Dict[int, List[WordCoordinate]], List[PageMetadata]]:
        """Get word coordinates and page metadata for citation mapping.

        Retrieves stored word coordinates from page metadata and converts
        them to WordCoordinate and PageMetadata objects for use with CitationMapper.

        Args:
            document_id: Document ID

        Returns:
            Tuple of (word_index, page_metadata) where:
            - word_index: Dict mapping page numbers to lists of WordCoordinate objects
            - page_metadata: List of PageMetadata objects for all pages
        """
        LOGGER.info(f"Loading word coordinates for document {document_id}")

        result = await self.session.execute(
            select(DocumentPage)
            .where(DocumentPage.document_id == document_id)
            .order_by(DocumentPage.page_number)
        )
        pages = result.scalars().all()

        if not pages:
            LOGGER.warning(f"No pages found for document {document_id}")
            return {}, []

        word_index: Dict[int, List[WordCoordinate]] = {}
        page_metadata_list: List[PageMetadata] = []
        total_words = 0

        for page in pages:
            page_num = page.page_number

            # Build page metadata
            width = float(page.width_points) if page.width_points else 612.0
            height = float(page.height_points) if page.height_points else 792.0
            rotation = page.rotation or 0

            page_metadata_list.append(PageMetadata(
                page_number=page_num,
                width=width,
                height=height,
                rotation=rotation,
            ))

            # Extract word coordinates from additional_metadata
            metadata = page.additional_metadata or {}
            word_coords = metadata.get("word_coordinates", [])

            if word_coords:
                word_index[page_num] = []
                for wc in word_coords:
                    word_index[page_num].append(WordCoordinate(
                        text=wc.get("t", ""),  # compact format: "t" for text
                        page_number=page_num,
                        x0=float(wc.get("x0", 0)),
                        y0=float(wc.get("y0", 0)),
                        x1=float(wc.get("x1", 0)),
                        y1=float(wc.get("y1", 0)),
                    ))
                total_words += len(word_index[page_num])

        LOGGER.info(
            f"Loaded word coordinates for citation mapping",
            extra={
                "document_id": str(document_id),
                "pages_with_coordinates": len(word_index),
                "total_words": total_words,
                "total_pages": len(page_metadata_list),
            }
        )

        return word_index, page_metadata_list

    async def get_page_dimensions(
        self,
        document_id: UUID
    ) -> Dict[int, Dict[str, Any]]:
        """Get page dimensions for a document.

        Args:
            document_id: Document ID

        Returns:
            Dict mapping page numbers to dimension info:
            {page_number: {"width": float, "height": float, "rotation": int}}
        """
        result = await self.session.execute(
            select(DocumentPage)
            .where(DocumentPage.document_id == document_id)
            .order_by(DocumentPage.page_number)
        )
        pages = result.scalars().all()

        dimensions = {}
        for page in pages:
            dimensions[page.page_number] = {
                "width": float(page.width_points) if page.width_points else 612.0,
                "height": float(page.height_points) if page.height_points else 792.0,
                "rotation": page.rotation or 0,
            }

        return dimensions
