"""Repository for page analysis data persistence.

This repository handles CRUD operations for page analysis, classifications,
and manifests.
"""

from typing import List, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from decimal import Decimal

from app.database.models import (
    PageAnalysis,
    PageClassificationResult,
    PageManifestRecord
)
from app.models.page_analysis_models import (
    PageSignals,
    PageClassification,
    PageManifest
)
from app.utils.logging import get_logger
from app.repositories.base_repository import BaseRepository

logger = get_logger(__name__)


class PageAnalysisRepository(BaseRepository[PageAnalysis]):
    """Repository for page analysis operations."""
    
    def __init__(self, session: AsyncSession):
        """Initialize repository with database session.
        
        Args:
            session: SQLAlchemy async session
        """
        self.session = session
    
    async def save_page_signals(
        self, 
        document_id: UUID, 
        signals: PageSignals
    ) -> PageAnalysis:
        """Save page signals to database.
        
        Args:
            document_id: Document UUID
            signals: PageSignals to save
            
        Returns:
            Created PageAnalysis record
        """
        page_analysis = PageAnalysis(
            document_id=document_id,
            page_number=signals.page_number,
            top_lines=signals.top_lines,
            text_density=Decimal(str(signals.text_density)),
            has_tables=signals.has_tables,
            max_font_size=Decimal(str(signals.max_font_size)) if signals.max_font_size else None,
            page_hash=signals.page_hash
        )
        
        self.session.add(page_analysis)
        await self.session.flush()
        
        logger.debug(
            f"Saved page signals for page {signals.page_number}",
            extra={"document_id": str(document_id), "page_number": signals.page_number}
        )
        
        return page_analysis
    
    async def save_page_classification(
        self,
        document_id: UUID,
        classification: PageClassification
    ) -> PageClassificationResult:
        """Save page classification to database.
        
        Args:
            document_id: Document UUID
            classification: PageClassification to save
            
        Returns:
            Created PageClassificationResult record
        """
        page_class = PageClassificationResult(
            document_id=document_id,
            page_number=classification.page_number,
            page_type=classification.page_type.value,
            confidence=Decimal(str(classification.confidence)),
            should_process=classification.should_process,
            duplicate_of=classification.duplicate_of,
            reasoning=classification.reasoning
        )
        
        self.session.add(page_class)
        await self.session.flush()
        
        logger.debug(
            f"Saved classification for page {classification.page_number}: {classification.page_type}",
            extra={
                "document_id": str(document_id),
                "page_number": classification.page_number,
                "page_type": classification.page_type
            }
        )
        
        return page_class
    
    async def save_manifest(self, manifest: PageManifest) -> PageManifestRecord:
        """Save or update page manifest in database (idempotent).
        
        Args:
            manifest: PageManifest to save
            
        Returns:
            Created or updated PageManifestRecord
        """
        # Check if manifest already exists
        stmt = select(PageManifestRecord).where(
            PageManifestRecord.document_id == manifest.document_id
        )
        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()
        
        if existing:
            # Update existing manifest
            existing.total_pages = manifest.total_pages
            existing.pages_to_process = manifest.pages_to_process
            existing.pages_skipped = manifest.pages_skipped
            existing.processing_ratio = Decimal(str(manifest.processing_ratio))
            
            await self.session.commit()
            
            logger.info(
                f"Updated page manifest for document {manifest.document_id}",
                extra={
                    "document_id": str(manifest.document_id),
                    "total_pages": manifest.total_pages,
                    "pages_to_process": len(manifest.pages_to_process),
                    "processing_ratio": float(manifest.processing_ratio),
                    "action": "update"
                }
            )
            
            return existing
        else:
            # Create new manifest
            manifest_record = PageManifestRecord(
                document_id=manifest.document_id,
                total_pages=manifest.total_pages,
                pages_to_process=manifest.pages_to_process,
                pages_skipped=manifest.pages_skipped,
                processing_ratio=Decimal(str(manifest.processing_ratio))
            )
            
            self.session.add(manifest_record)
            await self.session.commit()
            
            logger.info(
                f"Saved page manifest for document {manifest.document_id}",
                extra={
                    "document_id": str(manifest.document_id),
                    "total_pages": manifest.total_pages,
                    "pages_to_process": len(manifest.pages_to_process),
                    "processing_ratio": float(manifest.processing_ratio),
                    "action": "create"
                }
            )
            
            return manifest_record
    
    async def get_manifest(self, document_id: UUID) -> Optional[PageManifest]:
        """Retrieve page manifest for a document.
        
        Args:
            document_id: Document UUID
            
        Returns:
            PageManifest if found, None otherwise
        """
        stmt = select(PageManifestRecord).where(
            PageManifestRecord.document_id == document_id
        )
        result = await self.session.execute(stmt)
        record = result.scalar_one_or_none()
        
        if not record:
            return None
        
        # Get all classifications for this document
        classifications = await self.get_classifications(document_id)
        
        manifest = PageManifest(
            document_id=record.document_id,
            total_pages=record.total_pages,
            pages_to_process=record.pages_to_process,
            pages_skipped=record.pages_skipped,
            classifications=classifications
        )
        
        return manifest
    
    async def get_pages_to_process(self, document_id: UUID) -> List[int]:
        """Get list of page numbers that should be processed.
        
        Args:
            document_id: Document UUID
            
        Returns:
            List of page numbers to process
        """
        stmt = select(PageManifestRecord.pages_to_process).where(
            PageManifestRecord.document_id == document_id
        )
        result = await self.session.execute(stmt)
        pages = result.scalar_one_or_none()
        
        return pages if pages else []
    
    async def get_classifications(
        self, 
        document_id: UUID
    ) -> List[PageClassification]:
        """Get all page classifications for a document.
        
        Args:
            document_id: Document UUID
            
        Returns:
            List of PageClassification objects
        """
        stmt = select(PageClassificationResult).where(
            PageClassificationResult.document_id == document_id
        ).order_by(PageClassificationResult.page_number)
        
        result = await self.session.execute(stmt)
        records = result.scalars().all()
        
        classifications = [
            PageClassification(
                page_number=r.page_number,
                page_type=r.page_type,
                confidence=float(r.confidence),
                should_process=r.should_process,
                duplicate_of=r.duplicate_of,
                reasoning=r.reasoning
            )
            for r in records
        ]
        
        return classifications
    
    async def get_page_signals(
        self,
        document_id: UUID,
        page_number: int
    ) -> Optional[PageSignals]:
        """Get page signals for a specific page.
        
        Args:
            document_id: Document UUID
            page_number: Page number
            
        Returns:
            PageSignals if found, None otherwise
        """
        stmt = select(PageAnalysis).where(
            and_(
                PageAnalysis.document_id == document_id,
                PageAnalysis.page_number == page_number
            )
        )
        result = await self.session.execute(stmt)
        record = result.scalar_one_or_none()
        
        if not record:
            return None
        
        signals = PageSignals(
            page_number=record.page_number,
            top_lines=record.top_lines,
            text_density=float(record.text_density),
            has_tables=record.has_tables,
            max_font_size=float(record.max_font_size) if record.max_font_size else None,
            page_hash=record.page_hash
        )
        
        return signals
