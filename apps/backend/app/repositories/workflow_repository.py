import uuid
from typing import Optional, List, Sequence, Any
from datetime import datetime, timezone

from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Workflow, WorkflowDefinition, WorkflowDocument, WorkflowStageRun, WorkflowDocumentStageRun, WorkflowRunEvent, WorkflowQuery
from app.repositories.base_repository import BaseRepository


class WorkflowRepository(BaseRepository[Workflow]):
    """Repository for managing Workflow execution records."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, Workflow)

    async def get_by_id(self, id: uuid.UUID) -> Optional[Workflow]:
        """Get a workflow by ID with its definition loaded.
        
        This overrides the base implementation to provide eager loading
        of the workflow_definition relationship.
        """
        query = select(Workflow).where(Workflow.id == id).options(
            selectinload(Workflow.workflow_definition),
            selectinload(Workflow.stage_runs),
            selectinload(Workflow.events)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create_workflow(
        self,
        workflow_definition_id: Optional[uuid.UUID] = None,
        workflow_name: str = "Untitled",
        temporal_workflow_id: Optional[str] = None,
        status: str = "running",
        user_id: Optional[uuid.UUID] = None,
    ) -> Workflow:
        """Create a new workflow execution record.
        
        Args:
            workflow_definition_id: Optional workflow definition ID
            workflow_name: Name of the workflow instance
            temporal_workflow_id: Optional Temporal workflow ID
            status: Workflow status (default: "running")
            user_id: Optional user ID
            
        Returns:
            Created Workflow instance
        """
        return await self.create(
            workflow_definition_id=workflow_definition_id,
            workflow_name=workflow_name,
            temporal_workflow_id=temporal_workflow_id,
            status=status,
            user_id=user_id,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )

    async def update_workflow_name(
        self,
        workflow_id: uuid.UUID,
        workflow_name: str
    ) -> Workflow:
        """Update the name of a workflow.

        Args:
            workflow_id: Workflow record ID
            workflow_name: New name for the workflow

        Returns:
            Updated Workflow instance
        """
        workflow = await self.get_by_id(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        workflow.workflow_name = workflow_name
        workflow.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        return workflow

    async def get_all_with_definitions(
        self,
        skip: int = 0,
        limit: int = 100,
        filters: dict[str, Any] | None = None
    ) -> Sequence[Workflow]:
        """Get all workflows with their definitions loaded.
        
        Args:
            skip: Number of records to skip
            limit: Max records to return
            filters: Dictionary of filters
            
        Returns:
            List of Workflow instances with definition loaded
        """
        query = select(Workflow).options(selectinload(Workflow.workflow_definition))
        
        if filters:
            for key, value in filters.items():
                if hasattr(Workflow, key):
                    query = query.where(getattr(Workflow, key) == value)
        
        query = query.offset(skip).limit(limit).order_by(Workflow.created_at.desc(), Workflow.id.desc())
        
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_all_with_relationships(
        self,
        skip: int = 0,
        limit: int = 50,
        filters: Optional[dict[str, Any]] = None,
        include_documents: bool = True,
        include_stages: bool = True,
        include_events: bool = True
    ) -> Sequence[Workflow]:
        """Fetch workflows with selective eager loading of relationships."""
        query = select(Workflow).options(selectinload(Workflow.workflow_definition))
        
        if include_documents:
            query = query.options(
                selectinload(Workflow.workflow_documents).selectinload(WorkflowDocument.document)
            )
        
        if include_stages:
            query = query.options(selectinload(Workflow.stage_runs))
            
        if include_events:
            query = query.options(selectinload(Workflow.events))
            
        if filters:
            for key, value in filters.items():
                if hasattr(Workflow, key):
                    query = query.where(getattr(Workflow, key) == value)
                    
        query = query.offset(skip).limit(limit).order_by(Workflow.created_at.desc(), Workflow.id.desc())
        
        result = await self.session.execute(query)
        return result.scalars().all()

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

    async def emit_run_event(
        self,
        workflow_id: uuid.UUID,
        event_type: str,
        payload: Optional[dict] = None
    ) -> WorkflowRunEvent:
        """Create a new granular workflow run event.
        
        Args:
            workflow_id: Parent workflow ID
            event_type: Type of event (e.g. "workflow:progress")
            payload: Optional JSON payload for the event
            
        Returns:
            Created WorkflowRunEvent instance
        """
        event = WorkflowRunEvent(
            workflow_id=workflow_id,
            event_type=event_type,
            event_payload=payload,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        self.session.add(event)
        await self.session.flush()
        return event

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
        query = select(WorkflowDocument).where(
            WorkflowDocument.document_id == document_id
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

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

    async def get_documents_for_workflow(
        self,
        workflow_id: uuid.UUID
    ) -> List[Any]:
        """Get all documents associated with a workflow.
        
        Args:
            workflow_id: Workflow ID
            
        Returns:
            List of Document instances
        """
        query = select(WorkflowDocument).where(
            WorkflowDocument.workflow_id == workflow_id
        ).options(selectinload(WorkflowDocument.document))
        
        result = await self.session.execute(query)
        workflow_docs = result.scalars().all()
        
        return [wd.document for wd in workflow_docs if wd.document]


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

    async def get_by_definition_id(self, workflow_definition_id: uuid.UUID) -> Optional[WorkflowDefinition]:
        """Get a workflow definition by its ID.
        
        Args:
            workflow_definition_id: Workflow definition ID
            
        Returns:
            WorkflowDefinition if found, None otherwise
        """
        return await self.get_by_id(workflow_definition_id)


class WorkflowDocumentStageRunRepository(BaseRepository[WorkflowDocumentStageRun]):
    """Repository for managing document-level stage tracking records."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, WorkflowDocumentStageRun)

    async def get_by_workflow_and_document(
        self, workflow_id: uuid.UUID, document_id: uuid.UUID
    ) -> list[WorkflowDocumentStageRun]:
        """Get all stage runs for a specific document in a specific workflow.
        
        Args:
            workflow_id: Parent workflow ID
            document_id: ID of the document
            
        Returns:
            List of WorkflowDocumentStageRun instances
        """
        query = select(WorkflowDocumentStageRun).where(
            and_(
                WorkflowDocumentStageRun.workflow_id == workflow_id,
                WorkflowDocumentStageRun.document_id == document_id
            )
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update_status(
        self,
        stage_run_id: uuid.UUID,
        status: str,
        error_message: Optional[str] = None
    ) -> WorkflowDocumentStageRun:
        """Update the status of a document stage run.
        
        Args:
            stage_run_id: Record ID
            status: New status value
            error_message: Optional error message
            
        Returns:
            Updated WorkflowDocumentStageRun instance
        """
        stage_run = await self.get_by_id(stage_run_id)
        if not stage_run:
            raise ValueError(f"Stage run {stage_run_id} not found")
        
        stage_run.status = status
        stage_run.error_message = error_message
        if status == "completed":
            stage_run.completed_at = datetime.now(timezone.utc)
        
        self.session.add(stage_run)
        await self.session.flush()
        return stage_run


class WorkflowQueryRepository(BaseRepository[Any]):
    """Repository for managing WorkflowQuery records."""

    def __init__(self, session: AsyncSession):
        from app.database.models import WorkflowQuery
        super().__init__(session, WorkflowQuery)

    async def create_query(
        self,
        workflow_id: uuid.UUID,
        role: str,
        content: str,
        additional_metadata: Optional[dict] = None
    ) -> Any:
        """Create a new workflow query record.
        
        Args:
            workflow_id: Parent workflow ID
            role: sender role (user/model)
            content: Message content
            additional_metadata: Optional metadata
            
        Returns:
            Created WorkflowQuery instance
        """
  
        query = WorkflowQuery(
            workflow_id=workflow_id,
            role=role,
            content=content,
            additional_metadata=additional_metadata,
            created_at=datetime.now(timezone.utc)
        )
        self.session.add(query)
        await self.session.commit()

        return query


    async def get_by_workflow_id(
        self,
        workflow_id: uuid.UUID
    ) -> Sequence[Any]:
        """Get all queries for a workflow ordered by time.
        
        Args:
            workflow_id: Workflow ID
            
        Returns:
            List of WorkflowQuery instances
        """
        
        query = select(WorkflowQuery).where(
            WorkflowQuery.workflow_id == workflow_id
        ).order_by(WorkflowQuery.created_at.asc())
        
        result = await self.session.execute(query)
        return result.scalars().all()


