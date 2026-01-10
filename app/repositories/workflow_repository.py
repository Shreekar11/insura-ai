import uuid
from typing import Optional, List, Sequence, Any
from datetime import datetime, timezone

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Workflow, WorkflowDefinition, WorkflowDocument, WorkflowStageRun, WorkflowDocumentStageRun
from app.repositories.base_repository import BaseRepository


class WorkflowRepository(BaseRepository[Workflow]):
    """Repository for managing Workflow execution records."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, Workflow)

    async def create_workflow(
        self,
        workflow_definition_id: Optional[uuid.UUID] = None,
        temporal_workflow_id: Optional[str] = None,
        status: str = "running",
        user_id: Optional[uuid.UUID] = None,
    ) -> Workflow:
        """Create a new workflow execution record.
        
        Args:
            workflow_definition_id: Optional workflow definition ID
            temporal_workflow_id: Optional Temporal workflow ID
            status: Workflow status (default: "running")
            user_id: Optional user ID
            
        Returns:
            Created Workflow instance
        """
        return await self.create(
            workflow_definition_id=workflow_definition_id,
            temporal_workflow_id=temporal_workflow_id,
            status=status,
            user_id=user_id,
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

    async def update_status(
        self,
        workflow_id: uuid.UUID,
        status: str
    ) -> Workflow:
        """Update the status of a workflow.
        
        Args:
            workflow_id: Workflow record ID
            status: New status value
            
        Returns:
            Updated Workflow instance
        """
        workflow = await self.get_by_id(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")
        
        workflow.status = status
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
        self.session = session

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
        workflow_doc = WorkflowDocument(
            document_id=document_id,
            workflow_id=workflow_id,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        self.session.add(workflow_doc)
        await self.session.flush()
        return workflow_doc

    async def update_workflow_link(
        self,
        document_id: uuid.UUID,
        workflow_id: uuid.UUID
    ) -> WorkflowDocument:
        """Update the workflow_id in an existing workflow_document record.
        
        Args:
            document_id: ID of the document
            workflow_id: Workflow ID to link
            
        Returns:
            Updated WorkflowDocument instance
        """
        query = select(WorkflowDocument).where(
            and_(
                WorkflowDocument.document_id == document_id,
                WorkflowDocument.workflow_id.is_(None)
            )
        )
        result = await self.session.execute(query)
        workflow_doc = result.scalar_one_or_none()
        
        if not workflow_doc:
            raise ValueError(
                f"WorkflowDocument for document {document_id} with NULL workflow_id not found"
            )
        
        workflow_doc.workflow_id = workflow_id
        workflow_doc.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        return workflow_doc

    async def get_by_document_id(
        self,
        document_id: uuid.UUID
    ) -> Optional[WorkflowDocument]:
        """Get workflow_document by document_id.
        
        Args:
            document_id: Document ID
            
        Returns:
            WorkflowDocument if found, None otherwise
        """
        return await super().get_by_id(document_id)

    async def get_by_workflow_id(
        self,
        workflow_id: uuid.UUID
    ) -> List[WorkflowDocument]:
        """Get all workflow_documents for a workflow.
        
        Args:
            workflow_id: Workflow ID
            
        Returns:
            List of WorkflowDocument instances
        """
        query = select(WorkflowDocument).where(
            WorkflowDocument.workflow_id == workflow_id
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def get_by_workflow_and_document_id(
        self,
        workflow_id: uuid.UUID,
        document_id: uuid.UUID
    ) -> List[WorkflowDocument]:
        """Get all workflow_documents for a workflow.
        
        Args:
            workflow_id: Workflow ID
            
        Returns:
            List of WorkflowDocument instances
        """
        query = select(WorkflowDocument).where(
            WorkflowDocument.workflow_id == workflow_id,
            WorkflowDocument.document_id == document_id
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())


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

