"""Phase 2: OCR Extraction Pipeline with Docling.

Uses Docling as the primary parser with selective page processing.
Now accepts page_section_map from Phase 0 to store page_type metadata
with each extracted page, enabling section-aware downstream processing.

Also extracts word-level coordinates and page dimensions for citation
source mapping functionality.
"""

from typing import List, Optional, Dict
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.logging import get_logger
from app.models.page_data import PageData
from app.services.processed.services.ocr.ocr_service import OCRService
from app.services.processed.services.ocr.coordinate_extraction_service import (
    CoordinateExtractionService,
    get_coordinate_extraction_service,
)
from app.repositories.document_repository import DocumentRepository

LOGGER = get_logger(__name__)


class OCRExtractionPipeline:
    """OCR extraction pipeline using Docling for document parsing.

    Attributes:
        session: Database session for persistence
        doc_repo: Document repository for page storage
        ocr_service: Docling OCR service for extraction
        coordinate_service: Service for extracting word-level coordinates
        enable_coordinate_extraction: Whether to extract coordinates for citations
    """

    def __init__(
        self,
        session: AsyncSession,
        enable_coordinate_extraction: bool = True,
    ):
        """Initialize OCR extraction pipeline.

        Args:
            session: SQLAlchemy async session
            enable_coordinate_extraction: Whether to extract word coordinates
                for citation source mapping (default: True)
        """
        self.session = session
        self.doc_repo = DocumentRepository(session)
        self.ocr_service = OCRService()
        self.enable_coordinate_extraction = enable_coordinate_extraction
        self.coordinate_service = (
            get_coordinate_extraction_service()
            if enable_coordinate_extraction
            else None
        )

        LOGGER.info(
            "Initialized OCRExtractionPipeline with Docling backend",
            extra={
                "backend": "docling",
                "coordinate_extraction_enabled": enable_coordinate_extraction,
            }
        )

    async def extract_and_store_pages(
        self,
        document_id: UUID,
        document_url: str,
        pdf_bytes: Optional[bytes] = None,
    ) -> List[PageData]:
        """Extract text from document and store in database.

        Args:
            document_id: Document UUID
            document_url: URL or path to the document
            pdf_bytes: Optional PDF content as bytes for coordinate extraction.
                If not provided, coordinate extraction will be skipped.

        Returns:
            List[PageData]: Extracted page data with optional page dimensions
        """
        LOGGER.info(
            "Starting OCR extraction",
            extra={
                "document_id": str(document_id),
                "document_url": document_url,
                "has_pdf_bytes": pdf_bytes is not None,
            }
        )

        # Extract pages using Docling
        pages = await self.ocr_service.extract_pages(
            document_url=document_url,
            document_id=document_id,
        )

        # Extract coordinates and page dimensions if enabled and pdf_bytes provided
        page_dimensions = {}
        if self.enable_coordinate_extraction and self.coordinate_service and pdf_bytes:
            try:
                coord_result = await self.coordinate_service.extract_word_coordinates(
                    pdf_bytes
                )

                # Build page dimensions lookup
                for page_meta in coord_result.pages:
                    page_dimensions[page_meta.page_number] = {
                        "width": page_meta.width,
                        "height": page_meta.height,
                        "rotation": page_meta.rotation,
                    }

                LOGGER.info(
                    f"Extracted coordinates for {coord_result.total_pages} pages, "
                    f"{coord_result.total_words} words",
                    extra={
                        "document_id": str(document_id),
                        "total_pages": coord_result.total_pages,
                        "total_words": coord_result.total_words,
                    }
                )
            except Exception as e:
                LOGGER.warning(
                    f"Coordinate extraction failed, continuing without dimensions: {e}",
                    extra={"document_id": str(document_id), "error": str(e)}
                )

        # Add extraction metadata and page dimensions to pages
        for page in pages:
            if page.metadata is None:
                page.metadata = {}
            page.metadata["selective"] = False
            page.metadata["extraction_pipeline"] = "v2"

            # Add page dimensions if available
            if page.page_number in page_dimensions:
                dims = page_dimensions[page.page_number]
                page.width_points = dims["width"]
                page.height_points = dims["height"]
                page.rotation = dims["rotation"]

        # Store in database
        await self.doc_repo.store_pages(document_id, pages)

        LOGGER.info(
            f"OCR extraction complete: {len(pages)} pages stored",
            extra={
                "document_id": str(document_id),
                "pages_stored": len(pages),
                "pages_with_dimensions": len(page_dimensions),
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
