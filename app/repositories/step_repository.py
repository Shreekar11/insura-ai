from typing import Sequence, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import StepSectionOutput, StepEntityOutput
from app.repositories.base_repository import BaseRepository


class StepSectionOutputRepository(BaseRepository[StepSectionOutput]):
    """Repository for managing StepSectionOutput records."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, StepSectionOutput)

    async def get_by_document_and_workflow(
        self, document_id: UUID, workflow_id: UUID
    ) -> Sequence[StepSectionOutput]:
        """Get all section outputs for a specific document and workflow run.
        
        Args:
            document_id: The document UUID.
            workflow_id: The workflow run UUID.
            
        Returns:
            List of StepSectionOutput records.
        """
        query = select(self.model).where(
            self.model.document_id == document_id,
            self.model.workflow_id == workflow_id
        )
        result = await self.session.execute(query)
        return result.scalars().all()
    
    async def get_by_document_and_section(self, document_id: UUID, section_type: str) -> Optional[StepSectionOutput]:
        """Get a section output for a specific document and section name.
        
        Args:
            document_id: The document UUID.
            section_type: The section type.
            
        Returns:
            StepSectionOutput record.
        """
        query = select(self.model).where(
            self.model.document_id == document_id,
            self.model.section_type == section_type
        )
        result = await self.session.execute(query)
        return result.scalars().first()


class StepEntityOutputRepository(BaseRepository[StepEntityOutput]):
    """Repository for managing StepEntityOutput records."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, StepEntityOutput)

    async def get_by_document_and_workflow(
        self, document_id: UUID, workflow_id: UUID
    ) -> Sequence[StepEntityOutput]:
        """Get all entity outputs for a specific document and workflow run.
        
        Args:
            document_id: The document UUID.
            workflow_id: The workflow run UUID.
            
        Returns:
            List of StepEntityOutput records.
        """
        query = select(self.model).where(
            self.model.document_id == document_id,
            self.model.workflow_id == workflow_id
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_by_document_and_type(
        self, 
        document_id: UUID, 
        entity_type: str,
        workflow_id: Optional[UUID] = None
    ) -> Sequence[StepEntityOutput]:
        """Get entity outputs for a specific document and entity type.
        
        Args:
            document_id: The document UUID.
            entity_type: The entity type.
            workflow_id: Optional workflow UUID filter.
            
        Returns:
            List of StepEntityOutput records.
        """
        query = select(self.model).where(
            self.model.document_id == document_id,
            self.model.entity_type == entity_type
        )
        if workflow_id:
            query = query.where(self.model.workflow_id == workflow_id)
            
        result = await self.session.execute(query)
        return result.scalars().all()
