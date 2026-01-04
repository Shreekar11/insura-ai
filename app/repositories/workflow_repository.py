import uuid
from typing import Optional, List, Sequence
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Workflow, WorkflowDefinition, WorkflowDocument, WorkflowStageRun
from app.repositories.base_repository import BaseRepository

class WorkflowRepository(BaseRepository[Workflow]):
    """Repository for managing Workflow execution records."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, Workflow)

    async def create_workflow(
        self,
        workflow_document_id: uuid.UUID,
        workflow_definition_id: Optional[uuid.UUID] = None,
        temporal_workflow_id: Optional[str] = None,
        status: str = "running"
    ) -> Workflow:
        """Create a new workflow execution record.
        
        Args:
            workflow_document_id: ID of the workflow_document record
            workflow_definition_id: Optional workflow definition ID
            temporal_workflow_id: Optional Temporal workflow ID
            status: Workflow status (default: "running")
            
        Returns:
            Created Workflow instance
        """
        return await self.create(
            workflow_document_id=workflow_document_id,
            workflow_definition_id=workflow_definition_id,
            temporal_workflow_id=temporal_workflow_id,
            status=status,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )

    async def update_temporal_id(
        self,
        workflow_id: uuid.UUID,
        temporal_workflow_id: str
    ) -> Workflow:
        """Update the Temporal workflow ID for an existing workflow.
        
        Args:
            workflow_id: Workflow record ID
            temporal_workflow_id: Temporal workflow ID to set
            
        Returns:
            Updated Workflow instance
        """
        workflow = await self.get_by_id(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")
        
        workflow.temporal_workflow_id = temporal_workflow_id
        workflow.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        return workflow

    async def create_stage_run(
        self,
        workflow_id: uuid.UUID,
        stage_name: str,
        status: str = "pending"
    ) -> WorkflowStageRun:
        """Create a new stage run record.
        
        Args:
            workflow_id: Parent workflow ID
            stage_name: Name of the stage
            status: Stage status (default: "pending")
            
        Returns:
            Created WorkflowStageRun instance
        """
        stage_run = WorkflowStageRun(
            workflow_id=workflow_id,
            stage_name=stage_name,
            status=status,
            started_at=datetime.now(timezone.utc) if status == "running" else None
        )
        self.session.add(stage_run)
        await self.session.flush()
        return stage_run


class WorkflowDocumentRepository(BaseRepository[WorkflowDocument]):
    """Repository for managing WorkflowDocument join table records."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, WorkflowDocument)

    async def create_workflow_document(
        self,
        document_id: uuid.UUID,
        workflow_id: Optional[uuid.UUID] = None
    ) -> WorkflowDocument:
        """Create a workflow_document record.
        
        This creates the join table entry, initially without a workflow_id
        if the workflow hasn't been created yet.
        
        Args:
            document_id: ID of the document
            workflow_id: Optional workflow ID (can be None initially)
            
        Returns:
            Created WorkflowDocument instance
        """
        return await self.create(
            document_id=document_id,
            workflow_id=workflow_id,
            created_at=datetime.now(timezone.utc)
        )

    async def update_workflow_link(
        self,
        workflow_document_id: uuid.UUID,
        workflow_id: uuid.UUID
    ) -> WorkflowDocument:
        """Update the workflow_id in an existing workflow_document record.
        
        Args:
            workflow_document_id: ID of the workflow_document record
            workflow_id: Workflow ID to link
            
        Returns:
            Updated WorkflowDocument instance
        """
        workflow_doc = await self.get_by_id(workflow_document_id)
        if not workflow_doc:
            raise ValueError(f"WorkflowDocument {workflow_document_id} not found")
        
        workflow_doc.workflow_id = workflow_id
        await self.session.flush()
        return workflow_doc


class WorkflowDefinitionRepository(BaseRepository[WorkflowDefinition]):
    """Repository for managing WorkflowDefinition records."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, WorkflowDefinition)

    async def get_by_key(self, workflow_key: str) -> Optional[WorkflowDefinition]:
        """Get a workflow definition by its unique key.
        
        Args:
            workflow_key: Unique workflow key
            
        Returns:
            WorkflowDefinition if found, None otherwise
        """
        query = select(WorkflowDefinition).where(
            WorkflowDefinition.workflow_key == workflow_key
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()