"""Repository for section extraction persistence.

This repository handles persistence of section-level extraction outputs
from the Tier 2 extraction pipeline.
"""

from typing import List, Optional, Dict, Any
from uuid import UUID
from decimal import Decimal

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import SectionExtraction
from app.utils.logging import get_logger
from app.repositories.base_repository import BaseRepository

LOGGER = get_logger(__name__)


class SectionExtractionRepository(BaseRepository[SectionExtraction]):
    """Repository for managing section extraction records.
    
    This repository provides data access methods for section-level
    extraction outputs, including creation and querying by document/section.
    
    Attributes:
        session: SQLAlchemy async session for database operations
    """
    
    def __init__(self, session: AsyncSession):
        """Initialize section extraction repository.
        
        Args:
            session: SQLAlchemy async session
        """
        super().__init__(session, SectionExtraction)
        self.session = session
    
    async def create_section_extraction(
        self,
        document_id: UUID,
        workflow_id: UUID,
        section_type: str,
        extracted_fields: Dict[str, Any],
        page_range: Optional[Dict[str, int]] = None,
        confidence: Optional[Dict[str, Any]] = None,
        source_chunks: Optional[Dict[str, Any]] = None,
        pipeline_run_id: Optional[str] = None,
        model_version: Optional[str] = None,
        prompt_version: Optional[str] = None,
    ) -> SectionExtraction:
        """Create a new section extraction record.
        
        Args:
            document_id: Document ID
            workflow_id: Workflow ID
            section_type: Section type (e.g., "declarations", "coverages")
            extracted_fields: Raw extracted fields from LLM (JSONB)
            page_range: Page range dict with start/end
            confidence: Confidence metrics per field
            source_chunks: Source chunk references
            pipeline_run_id: Pipeline execution identifier
            model_version: LLM model version
            prompt_version: Prompt template version
            
        Returns:
            Created SectionExtraction record
        """
        extraction = await self.create(
            document_id=document_id,
            workflow_id=workflow_id,
            section_type=section_type,
            extracted_fields=extracted_fields,
            page_range=page_range,
            confidence=confidence,
            source_chunks=source_chunks,
            pipeline_run_id=pipeline_run_id,
            model_version=model_version,
            prompt_version=prompt_version,
        )
        
        LOGGER.debug(
            "Created section extraction",
            extra={
                "document_id": str(document_id),
                "section_type": section_type,
                "extraction_id": str(extraction.id),
            }
        )
        
        return extraction
    
    async def get_by_document(
        self,
        document_id: UUID,
        section_type: Optional[str] = None,
        workflow_id: Optional[UUID] = None,
    ) -> List[SectionExtraction]:
        """Get section extractions for a document.
        
        Args:
            document_id: Document ID
            section_type: Optional section type filter
            workflow_id: Optional workflow ID filter
            
        Returns:
            List of SectionExtraction records
        """
        stmt = select(SectionExtraction).where(
            SectionExtraction.document_id == document_id
        )
        
        if section_type:
            stmt = stmt.where(SectionExtraction.section_type == section_type)
            
        if workflow_id:
            stmt = stmt.where(SectionExtraction.workflow_id == workflow_id)
        
        stmt = stmt.order_by(SectionExtraction.created_at)
        
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_document_and_workflow(self, document_id: UUID, workflow_id: UUID) -> List[SectionExtraction]:
        """Get section extractions for a document and workflow.
        
        Args:
            document_id: Document ID
            workflow_id: Workflow ID
            
        Returns:
            List of SectionExtraction records
        """
        stmt = select(SectionExtraction).where(
            SectionExtraction.document_id == document_id,
            SectionExtraction.workflow_id == workflow_id,
        )
        
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_document_by_section(self, document_id: UUID, section_type: str) -> List[SectionExtraction]:
        """Get section extractions for a document and section type.
        
        Args:
            document_id: Document ID
            section_type: Section type
            
        Returns:
            List of SectionExtraction records
        """
        stmt = select(SectionExtraction).where(
            SectionExtraction.document_id == document_id,
            SectionExtraction.section_type == section_type,
        )
        
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
    
    async def get_by_id(self, extraction_id: UUID) -> Optional[SectionExtraction]:
        """Get section extraction by ID.
        
        Args:
            extraction_id: Extraction ID
            
        Returns:
            SectionExtraction or None
        """
        return await super().get_by_id(extraction_id)

