"""Phase 2: OCR Extraction Pipeline with Docling.

Uses Docling as the primary parser with selective page processing.
Now accepts page_section_map from Phase 0 to store page_type metadata
with each extracted page, enabling section-aware downstream processing.
"""

from typing import List, Optional, Dict
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.logging import get_logger
from app.models.page_data import PageData
from app.services.processed.services.ocr.ocr_service import OCRService
from app.repositories.document_repository import DocumentRepository

LOGGER = get_logger(__name__)


class OCRExtractionPipeline:
    """OCR extraction pipeline using Docling for document parsing.
    
    Attributes:
        session: Database session for persistence
        doc_repo: Document repository for page storage
        docling_service: Docling OCR service for extraction
    """
    
    def __init__(self, session: AsyncSession):
        """Initialize OCR extraction pipeline.
        
        Args:
            session: SQLAlchemy async session
        """
        self.session = session
        self.doc_repo = DocumentRepository(session)
        self.ocr_service = OCRService()
        
        LOGGER.info(
            "Initialized OCRExtractionPipeline with Docling backend",
            extra={"backend": "docling"}
        )

    async def extract_and_store_pages(
        self, 
        document_id: UUID, 
        document_url: str,
    ) -> List[PageData]:
        """Extract text from document and store in database.
        
        Args:
            document_id: Document UUID
            document_url: URL or path to the document
        
        Returns:
            List[PageData]: Extracted page data
        """
        LOGGER.info(
            "Starting OCR extraction",
            extra={
                "document_id": str(document_id),
                "document_url": document_url,
            }
        )
        
        # Extract pages using Docling
        pages = await self.ocr_service.extract_pages(
            document_url=document_url,
            document_id=document_id,
        )
        
        # Add extraction metadata to pages
        for page in pages:
            if page.metadata is None:
                page.metadata = {}
            page.metadata["selective"] = False
            page.metadata["extraction_pipeline"] = "v2"
        
        # Store in database
        await self.doc_repo.store_pages(document_id, pages)
        
        LOGGER.info(
            f"OCR extraction complete: {len(pages)} pages stored",
            extra={
                "document_id": str(document_id),
                "pages_stored": len(pages),
                "page_numbers": [p.page_number for p in pages]
            }
        )
        
        return pages
    
    async def extract_pages_only(
        self,
        document_id: UUID,
        document_url: str,
    ) -> List[PageData]:
        """Extract pages without storing to database.
        
        Useful for preview or validation scenarios.
        
        Args:
            document_id: Document UUID
            document_url: URL or path to the document
        
        Returns:
            List[PageData]: Extracted page data (not stored)
        """
        return await self.ocr_service.extract_pages(
            document_url=document_url,
            document_id=document_id,
        )
