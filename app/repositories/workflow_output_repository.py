"""Repository for workflow outputs."""

from uuid import UUID
from typing import Optional
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from decimal import Decimal

from app.database.models import WorkflowOutput
from app.repositories.base_repository import BaseRepository


class WorkflowOutputRepository(BaseRepository[WorkflowOutput]):
    """Repository for managing workflow outputs."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, WorkflowOutput)

    async def create_output(
        self,
        workflow_id: UUID,
        workflow_name: str,
        status: str,
        result: dict,
        workflow_definition_id: Optional[UUID] = None,
        confidence: Optional[Decimal] = None,
        output_metadata: Optional[dict] = None,
    ) -> WorkflowOutput:
        """Create a new workflow output record.
        
        Args:
            workflow_id: UUID of the workflow execution
            workflow_name: Name of the workflow (e.g., 'policy_comparison')
            status: Output status (COMPLETED, COMPLETED_WITH_WARNINGS, FAILED, NEEDS_REVIEW)
            result: Workflow-specific output payload (JSONB)
            workflow_definition_id: Optional UUID of the workflow definition
            confidence: Optional overall confidence score (0.0-1.0)
            metadata: Optional additional context (HITL flags, warnings, etc.)
            
        Returns:
            Created WorkflowOutput instance
        """
        return await self.create(
            workflow_id=workflow_id,
            workflow_definition_id=workflow_definition_id,
            workflow_name=workflow_name,
            status=status,
            confidence=confidence,
            result=result,
            output_metadata=output_metadata or {},
        )

    async def get_by_workflow_id(self, workflow_id: UUID) -> Optional[WorkflowOutput]:
        """Retrieve workflow output by workflow ID.
        
        Args:
            workflow_id: UUID of the workflow execution
            
        Returns:
            WorkflowOutput instance if found, None otherwise
        """
        stmt = select(WorkflowOutput).where(WorkflowOutput.workflow_id == workflow_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_workflow_name(
        self, workflow_name: str, limit: int = 10
    ) -> list[WorkflowOutput]:
        """Retrieve recent workflow outputs by workflow name.
        
        Args:
            workflow_name: Name of the workflow (e.g., 'policy_comparison')
            limit: Maximum number of results to return (default: 10)
            
        Returns:
            List of WorkflowOutput instances, ordered by created_at descending
        """
        stmt = (
            select(WorkflowOutput)
            .where(WorkflowOutput.workflow_name == workflow_name)
            .order_by(desc(WorkflowOutput.created_at))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_status(
        self,
        output_id: UUID,
        status: str,
        output_metadata: Optional[dict] = None,
    ) -> Optional[WorkflowOutput]:
        """Update workflow output status and metadata.
        
        Useful for HITL review workflows where status changes from
        NEEDS_REVIEW to COMPLETED after human approval.
        
        Args:
            output_id: UUID of the workflow output
            status: New status value
            metadata: Optional metadata to merge with existing metadata
            
        Returns:
            Updated WorkflowOutput instance if found, None otherwise
        """
        output = await self.get_by_id(output_id)
        if not output:
            return None

        output.status = status
        if output_metadata:
            # Merge new metadata with existing
            output.output_metadata = {**(output.output_metadata or {}), **output_metadata}

        await self.session.flush()
        return output

    async def get_by_id(self, output_id: UUID) -> Optional[WorkflowOutput]:
        """Retrieve workflow output by ID.
        
        Args:
            output_id: UUID of the workflow output
            
        Returns:
            WorkflowOutput instance if found, None otherwise
        """
        stmt = select(WorkflowOutput).where(WorkflowOutput.id == output_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
