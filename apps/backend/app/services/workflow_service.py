"""Workflow service for orchestrating document processing pipelines."""

from uuid import UUID
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.document_repository import DocumentRepository
from app.repositories.workflow_repository import (
    WorkflowRepository,
    WorkflowDefinitionRepository,
    WorkflowDocumentRepository,
)
from app.repositories.stages_repository import StagesRepository
from fastapi import UploadFile
from app.temporal.shared.workflows.process_document import ProcessDocumentWorkflow
from app.utils.logging import get_logger
from app.services.base_service import BaseService
from app.services.storage_service import StorageService
from app.core.exceptions import ValidationError, AppError
from app.schemas.generated.workflows import Workflow, WorkflowResponse, WorkflowExecutionResponse
from app.repositories.section_extraction_repository import SectionExtractionRepository
from app.repositories.step_repository import StepEntityOutputRepository, StepSectionOutputRepository
from app.core.temporal_client import get_temporal_client

LOGGER = get_logger(__name__)


class WorkflowService(BaseService):
    """Service for managing document processing workflows.
    
    Coordinates between database repositories and Temporal client.
    Extends BaseService to leverage standardized execution flow.
    """

    def __init__(self, session: AsyncSession):
        """Initialize workflow service with database session.
        
        Args:
            session: Async database session for repository access
        """
        super().__init__()
        self.session = session
        self.doc_repo = DocumentRepository(session)
        self.wf_repo = WorkflowRepository(session)
        self.wf_doc_repo = WorkflowDocumentRepository(session)
        self.def_repo = WorkflowDefinitionRepository(session)
        self.stage_repo = StagesRepository(session)
        self.extraction_repo = SectionExtractionRepository(session)
        self.step_entity_output_repo = StepEntityOutputRepository(session)
        self.step_section_output_repo = StepSectionOutputRepository(session)
        self.storage_service = StorageService()

    async def run(self, *args, **kwargs) -> Any:
        """Route to appropriate handler based on action.
        
        This implements the abstract run() method from BaseService.
        It acts as a dispatcher to specific workflow operations.
        """
        action = kwargs.get("action")
        
        if action == "start_extraction":
            return await self._start_extraction_workflow(
                kwargs.get("pdf_url"),
                kwargs.get("user_id")
            )
        elif action == "get_status":
            return await self._get_workflow_status(kwargs.get("workflow_id"))
        elif action == "execute_workflow":
            return await self._execute_generic_workflow(
                kwargs.get("workflow_key"),
                kwargs.get("document_ids"),
                kwargs.get("user_id"),
                kwargs.get("workflow_name"),
                kwargs.get("metadata"),
                kwargs.get("workflow_id")
            )
        elif action == "create_workflow":
            return await self._create_workflow_logic(
                kwargs.get("workflow_definition_id"),
                kwargs.get("user_id"),
                kwargs.get("workflow_name")
            )
        elif action == "update_workflow":
            return await self._update_workflow_logic(
                kwargs.get("workflow_id"),
                kwargs.get("workflow_name")
            )
        else:
            raise ValidationError(f"Unknown action: {action}")

    async def execute_start_extraction(
        self, 
        pdf_url: str, 
        user_id: UUID
    ) -> Dict[str, Any]:
        """Execute document extraction workflow with validation and error handling.
        
        This method leverages BaseService.execute() for standardized flow:
        1. Validation
        2. Core logic execution
        3. Error handling
        
        Args:
            pdf_url: URL of the PDF document to process
            user_id: ID of the user initiating the workflow
            
        Returns:
            Dict containing workflow details and status
            
        Raises:
            ValidationError: If inputs are invalid
            AppError: If workflow start fails
        """
        return await self.execute(
            action="start_extraction",
            pdf_url=pdf_url,
            user_id=user_id
        )

    async def execute_get_status(self, workflow_id: str) -> Dict[str, Any]:
        """Execute workflow status query with validation and error handling.
        
        Args:
            workflow_id: Temporal workflow ID to query
            
        Returns:
            Dict containing workflow status information
            
        Raises:
            ValidationError: If workflow_id is invalid
            AppError: If status query fails
        """
        return await self.execute(
            action="get_status",
            workflow_id=workflow_id
        )

    async def execute_workflow(
        self,
        workflow_key: str,
        document_ids: List[UUID],
        user_id: UUID,
        workflow_name: str = "Untitled",
        metadata: Optional[Dict[str, Any]] = None,
        workflow_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """Execute a generic workflow by its key.
        
        Args:
            workflow_key: Key of the workflow definition to execute
            document_ids: List of document IDs involved
            user_id: ID of the user initiating the workflow
            workflow_name: Name of the workflow instance
            metadata: Optional metadata for the workflow
            workflow_id: Optional existing workflow ID
            
        Returns:
            Dict containing workflow details and status
        """
        return await self.execute(
            action="execute_workflow",
            workflow_key=workflow_key,
            document_ids=document_ids,
            user_id=user_id,
            workflow_name=workflow_name,
            metadata=metadata,
            workflow_id=workflow_id
        )

    async def execute_create_workflow(
        self,
        workflow_definition_id: UUID,
        user_id: UUID,
        workflow_name: str = "Untitled"
    ) -> Dict[str, Any]:
        """Create a draft workflow execution.
        
        Args:
            workflow_definition_id: ID of definition
            user_id: User ID
            workflow_name: Name of workflow
            
        Returns:
            Dict containing workflow details
        """
        return await self.execute(
            action="create_workflow",
            user_id=user_id,
            workflow_definition_id=workflow_definition_id,
            workflow_name=workflow_name
        )

    async def execute_update_workflow(
        self,
        workflow_id: UUID,
        workflow_name: str,
        user_id: UUID
    ) -> Dict[str, Any]:
        """Update an existing workflow.

        Args:
            workflow_id: Workflow ID
            workflow_name: New name
            user_id: User ID (for validation/access check if needed, though currently unused for direct update)

        Returns:
            Dict containing updated workflow details
        """
        return await self.execute(
            action="update_workflow",
            workflow_id=workflow_id,
            workflow_name=workflow_name,
            user_id=user_id
        )

    def validate(self, *args, **kwargs):
        """Validate service inputs based on the action being performed.
        
        Raises:
            ValidationError: If validation fails
        """
        action = kwargs.get("action")
        
        if action == "start_extraction":
            self._validate_start_extraction(
                kwargs.get("pdf_url"),
                kwargs.get("user_id")
            )
        elif action == "get_status":
            self._validate_get_status(kwargs.get("workflow_id"))
        elif action == "execute_workflow":
            if not kwargs.get("workflow_key"):
                raise ValidationError("workflow_key is required")
            if not kwargs.get("document_ids"):
                raise ValidationError("document_ids are required")
            if not kwargs.get("user_id"):
                raise ValidationError("user_id is required")
            if not kwargs.get("workflow_name"):
                raise ValidationError("workflow_name is required")
        elif action == "create_workflow":
            if not kwargs.get("workflow_definition_id"):
                raise ValidationError("workflow_definition_id is required")
            if not kwargs.get("user_id"):
                raise ValidationError("user_id is required")
            if not kwargs.get("workflow_name"):
                raise ValidationError("workflow_name is required")
        elif action == "update_workflow":
            if not kwargs.get("workflow_id"):
                raise ValidationError("workflow_id is required")
            if not kwargs.get("workflow_name"):
                raise ValidationError("workflow_name is required")

    def _validate_start_extraction(
        self, 
        pdf_url: Optional[str], 
        user_id: Optional[UUID]
    ):
        """Validate inputs for starting extraction workflow.
        
        Args:
            pdf_url: URL of the PDF document
            user_id: User ID initiating the workflow
            
        Raises:
            ValidationError: If inputs are invalid
        """
        if not pdf_url:
            raise ValidationError("pdf_url is required")
        
        if not isinstance(pdf_url, str) or len(pdf_url.strip()) == 0:
            raise ValidationError("pdf_url must be a non-empty string")
        
        if not pdf_url.startswith(("http://", "https://")):
            raise ValidationError("pdf_url must be a valid HTTP/HTTPS URL")
        
        if not user_id:
            raise ValidationError("user_id is required")
        
        if not isinstance(user_id, UUID):
            raise ValidationError("user_id must be a valid UUID")

    def _validate_get_status(self, workflow_id: Optional[str]):
        """Validate inputs for getting workflow status.
        
        Args:
            workflow_id: Workflow ID to query
            
        Raises:
            ValidationError: If workflow_id is invalid
        """
        if not workflow_id:
            raise ValidationError("workflow_id is required")
        
        if not isinstance(workflow_id, str) or len(workflow_id.strip()) == 0:
            raise ValidationError("workflow_id must be a non-empty string")


    async def _start_extraction_workflow(
        self,
        pdf_url: str,
        user_id: UUID
    ) -> Dict[str, Any]:
        """Core logic for starting document extraction workflow.
        
        Orchestrates:
        1. Workflow definition creation/retrieval
        2. Workflow execution record creation
        3. Document record creation
        4. Document-workflow linkage
        5. Temporal workflow initiation
        6. Temporal ID persistence
        
        Args:
            pdf_url: URL of the PDF document to process
            user_id: ID of the user initiating the workflow
            
        Returns:
            Dict containing workflow details and status
            
        Raises:
            AppError: If any step fails
        """
        try:
            # Step 1: Ensure workflow definition exists
            workflow_key = "document_extraction"
            definition = await self.def_repo.get_by_key(workflow_key)
            if not definition:
                self.logger.info(f"Creating workflow definition: {workflow_key}")
                definition = await self.def_repo.create(
                    workflow_key=workflow_key,
                    display_name="Document Extraction",
                    description="OCR, classification, section extraction, and enrichment",
                    supports_multi_docs=False,
                )

            # Step 2: Create workflow execution
            self.logger.info(f"Creating workflow run for definition: {definition.id}")
            workflow_run = await self.wf_repo.create_workflow(
                workflow_definition_id=definition.id,
                workflow_name="Document Extraction",
                status="running",
                user_id=user_id,
            )
            workflow_id = workflow_run.id

            # Step 3: Create document record
            self.logger.info(f"Creating document record for URL: {pdf_url}")
            document = await self.doc_repo.create_document(
                file_path=pdf_url,
                page_count=0,
                user_id=user_id,
            )
            document_id = document.id

            # Step 4: Link document to workflow
            self.logger.info(
                f"Linking document {document_id} to workflow {workflow_id}"
            )
            await self.wf_doc_repo.create_workflow_document(
                workflow_id=workflow_id,
                document_id=document_id,
            )

            # Commit database changes before interacting with Temporal
            await self.session.commit()
            self.logger.info("Database changes committed successfully")

            # Step 5: Start Temporal workflow
            self.logger.info(f"Starting Temporal workflow for workflow_id: {workflow_id}")
            temporal_client = await get_temporal_client()
            workflow_handle = await temporal_client.start_workflow(
                ProcessDocumentWorkflow.run,
                {
                    "workflow_id": str(workflow_id),
                    "documents": [
                        {
                            "document_id": str(document_id),
                            "url": pdf_url,
                        }
                    ],
                },
                id=f"workflow-{workflow_id}",
                task_queue="documents-queue",
            )

            # Step 6: Update with Temporal ID
            self.logger.info(
                f"Updating workflow {workflow_id} with Temporal ID: {workflow_handle.id}"
            )
            await self.wf_repo.update_temporal_id(
                workflow_id=workflow_id,
                temporal_workflow_id=workflow_handle.id,
            )
            await self.session.commit()

            self.logger.info(
                f"Workflow started successfully: {workflow_id} (Temporal: {workflow_handle.id})"
            )

            return {
                "workflow_id": str(workflow_id),
                "documents": [str(document_id)],
                "temporal_id": workflow_handle.id,
                "status": "processing",
                "message": "Document extraction workflow started.",
            }

        except Exception as e:
            self.logger.error(
                f"Failed to start extraction workflow: {str(e)}",
                exc_info=True,
                extra={
                    "pdf_url": pdf_url,
                    "user_id": str(user_id),
                }
            )
            await self.session.rollback()
            raise AppError(
                f"Failed to start extraction workflow: {str(e)}",
                original_error=e
            )

    async def _get_workflow_status(self, workflow_id: str) -> Dict[str, Any]:
        """Query Temporal for current workflow status.
        
        Args:
            workflow_id: Temporal workflow ID to query
            
        Returns:
            Dict containing workflow status information
            
        Raises:
            AppError: If status query fails
        """
        try:
            self.logger.info(f"Querying status for workflow: {workflow_id}")
            temporal_client = await get_temporal_client()
            handle = temporal_client.get_workflow_handle(workflow_id)
            status_data = await handle.query("get_status")
            
            self.logger.info(
                f"Retrieved status for workflow {workflow_id}: {status_data.get('status')}"
            )
            
            return {
                "workflow_id": workflow_id,
                "status": status_data.get("status", "unknown"),
                "current_phase": status_data.get("current_phase"),
                "progress": status_data.get("progress", 0.0),
            }
            
        except Exception as e:
            self.logger.error(
                f"Failed to query workflow status: {str(e)}",
                exc_info=True,
                extra={"workflow_id": workflow_id}
            )
            raise AppError(
                f"Failed to query workflow status for {workflow_id}: {str(e)}",
                original_error=e
            )

    async def start_extraction_workflow(
        self, 
        pdf_url: str, 
        user_id: UUID
    ) -> Dict[str, Any]:
        """Legacy method for starting extraction workflow.
        
        Maintained for backward compatibility. New code should use
        execute_start_extraction() for BaseService benefits.
        
        Args:
            pdf_url: URL of the PDF document to process
            user_id: ID of the user initiating the workflow
            
        Returns:
            Dict containing workflow details and status
        """
        return await self.execute_start_extraction(pdf_url, user_id)

    async def get_workflow_status(self, workflow_id: str) -> Dict[str, Any]:
        """Legacy method for getting workflow status.
        
        Maintained for backward compatibility. New code should use
        execute_get_status() for BaseService benefits.
        
        Args:
            workflow_id: Temporal workflow ID to query
            
        Returns:
            Dict containing workflow status information
        """
        return await self.execute_get_status(workflow_id)

    async def get_all_document_stages(self) -> List[Any]:
        """Get completion status of all processing stages for all documents.
        
        Returns:
            List of document stage records
        """
        try:
            self.logger.info("Retrieving all document stages")
            return await self.stage_repo.get_all_document_stages()
        except Exception as e:
            self.logger.error(
                f"Failed to get all document stages: {str(e)}",
                exc_info=True
            )
            raise AppError(
                f"Failed to retrieve document stages: {str(e)}",
                original_error=e
            )

    async def get_document_stage(
        self, 
        document_id: UUID, 
        workflow_id: Optional[UUID] = None
    ) -> List[Any]:
        """Get completion status of all processing stages for a document.
        
        Args:
            document_id: ID of the document to query
            workflow_id: Optional workflow ID to filter by
            
        Returns:
            List of stage records for the document
        """
        try:
            self.logger.info(
                f"Retrieving stages for document: {document_id}",
                extra={"workflow_id": str(workflow_id) if workflow_id else None}
            )
            result = await self.stage_repo.get_document_stage(document_id, workflow_id)
            LOGGER.info(f"[WorkflowService] Retrieved stages: {result}")

            return result
        except Exception as e:
            self.logger.error(
                f"Failed to get document stages: {str(e)}",
                exc_info=True,
                extra={
                    "document_id": str(document_id),
                    "workflow_id": str(workflow_id) if workflow_id else None
                }
            )
            raise AppError(
                f"Failed to retrieve stages for document {document_id}: {str(e)}",
                original_error=e
            )

    async def _update_workflow_logic(
        self,
        workflow_id: UUID,
        workflow_name: str
    ) -> Dict[str, Any]:
        """Core logic for updating a workflow.

        Args:
            workflow_id: Workflow ID
            workflow_name: New name

        Returns:
            Dict containing updated workflow details
        """
        try:
            workflow = await self.wf_repo.update_workflow_name(
                workflow_id=workflow_id,
                workflow_name=workflow_name
            )
            await self.session.commit()

            # Return standard workflow response format (similar to get_workflow_details)
            return await self.get_workflow_details(workflow.id, workflow.user_id)

        except Exception as e:
            self.logger.error(f"Failed to update workflow {workflow_id}: {e}", exc_info=True)
            await self.session.rollback()
            raise AppError(f"Failed to update workflow: {e}", original_error=e)

    async def _execute_generic_workflow(
        self,
        workflow_key: str,
        document_ids: List[UUID],
        user_id: UUID,
        workflow_name: str = "Untitled",
        metadata: Optional[Dict[str, Any]] = None,
        workflow_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """Core logic for executing a generic workflow.
        
        Args:
            workflow_key: Key of the workflow definition
            document_ids: List of document IDs
            user_id: User ID
            workflow_name: Name of the workflow instance
            metadata: Optional metadata
            workflow_id: Optional existing workflow ID
            
        Returns:
            Dict containing workflow details and status
        """
        try:
            # Step 1: Get workflow definition
            definition = await self.def_repo.get_by_key(workflow_key)
            if not definition:
                raise ValidationError(f"Workflow definition {workflow_key} not found")
 
            # Step 2: Create or fetch workflow execution record
            if workflow_id:
                self.logger.info(f"Resuming existing workflow run: {workflow_id}")
                workflow_run = await self.wf_repo.get_by_id(workflow_id)
                if not workflow_run:
                    raise ValidationError(f"Workflow {workflow_id} not found")
                
                # Update status to running
                await self.wf_repo.update_status(workflow_id, "running")
                # Update name if different
                if workflow_name != workflow_run.workflow_name:
                    workflow_run.workflow_name = workflow_name
            else:
                self.logger.info(f"Creating workflow run for generic workflow: {workflow_key}")
                workflow_run = await self.wf_repo.create_workflow(
                    workflow_definition_id=definition.id,
                    workflow_name=workflow_name,
                    status="running",
                    user_id=user_id,
                )
            
            workflow_id = workflow_run.id

            # Step 3: Link documents to workflow
            documents_data = []
            for doc_id in document_ids:
                doc = await self.doc_repo.get_by_id(doc_id)
                if not doc:
                    raise ValidationError(f"Document {doc_id} not found")

                documents_data.append({
                    "document_id": str(doc_id),
                    "url": doc.file_path,
                    "document_name": doc.document_name or doc.file_path.split("/")[-1]
                })

            # Commit database changes before Temporal
            await self.session.commit()

            # Step 4: Start Temporal workflow
            self.logger.info(f"Starting Temporal workflow for {workflow_key}: {workflow_id}")
            temporal_client = await get_temporal_client()
            
            # Map workflow key to workflow class
            from app.temporal.product.policy_comparison.workflows.policy_comparison import PolicyComparisonWorkflow
            from app.temporal.product.proposal_generation.workflows.proposal_generation import ProposalGenerationWorkflow
            from app.temporal.shared.workflows.process_document import ProcessDocumentWorkflow
            workflow_class_map = {
                "policy_comparison": PolicyComparisonWorkflow,
                "proposal_generation": ProposalGenerationWorkflow,
                "document_extraction": ProcessDocumentWorkflow,
            }
            
            wf_class = workflow_class_map.get(workflow_key)
            if not wf_class:
                raise ValidationError(f"Temporal workflow not implemented for key: {workflow_key}")

            from temporalio.exceptions import WorkflowAlreadyStartedError
            
            try:
                workflow_handle = await temporal_client.start_workflow(
                    wf_class.run,
                    {
                        "workflow_id": str(workflow_id),
                        "workflow_definition_id": str(definition.id),
                        "workflow_name": workflow_key,
                        "documents": documents_data,
                        "metadata": metadata or {},
                    },
                    id=f"workflow-{workflow_id}",
                    task_queue="documents-queue",
                )
            except WorkflowAlreadyStartedError:
                self.logger.info(f"Temporal workflow workflow-{workflow_id} already running, getting handle.")
                workflow_handle = temporal_client.get_workflow_handle(f"workflow-{workflow_id}")

            # Step 5: Update with Temporal ID
            await self.wf_repo.update_temporal_id(
                workflow_id=workflow_id,
                temporal_workflow_id=workflow_handle.id,
            )
            await self.session.commit()

            return {
                "workflow_id": str(workflow_id),
                "document_ids": [str(d) for d in document_ids],
                "temporal_id": workflow_handle.id,
                "status": "processing",
                "message": f"{definition.display_name} started successfully.",
            }

        except Exception as e:
            self.logger.error(
                f"Failed to execute generic workflow {workflow_key}: {str(e)}",
                exc_info=True,
                extra={"user_id": str(user_id)}
            )
            await self.session.rollback()
            raise AppError(
                f"Failed to execute generic workflow {workflow_key}: {str(e)}",
                original_error=e
            )

    async def list_workflows(
        self, 
        user_id: UUID, 
        limit: int = 50, 
        offset: int = 0,
        include_documents: bool = True,
        include_stages: bool = True,
        include_events: bool = True,
        events_limit: int = 5
    ) -> Dict[str, Any]:
        """List workflows with comprehensive dashboard data."""
        filters = {"user_id": user_id}
        workflows = await self.wf_repo.get_all_with_relationships(
            skip=offset, 
            limit=limit, 
            filters=filters,
            include_documents=include_documents,
            include_stages=include_stages,
            include_events=include_events
        )
        total = await self.wf_repo.count(filters=filters)
        
        workflow_items = []
        for wf in workflows:
            item = await self._build_workflow_list_item(
                wf, 
                include_documents=include_documents,
                include_stages=include_stages,
                include_events=include_events,
                events_limit=events_limit
            )
            workflow_items.append(item)
            
        return {
            "total": total,
            "workflows": workflow_items
        }

    async def _build_workflow_list_item(
        self,
        workflow: Any,
        include_documents: bool,
        include_stages: bool,
        include_events: bool,
        events_limit: int = 5
    ) -> Dict[str, Any]:
        """Build enhanced workflow item with metrics."""
        
        # Calculate metrics
        metrics = await self._calculate_workflow_metrics(workflow)
        
        # Build documents list
        documents = []
        if include_documents and workflow.workflow_documents:
            for wd in workflow.workflow_documents:
                doc = wd.document
                documents.append({
                    "document_id": doc.id,
                    "document_name": doc.document_name or doc.file_path.split("/")[-1],
                    "file_name": doc.document_name or doc.file_path.split("/")[-1],
                    "page_count": doc.page_count,
                    "status": doc.status,
                    "uploaded_at": doc.uploaded_at
                })
                
        # Build stages list
        stages = []
        if include_stages and workflow.stage_runs:
            for sr in workflow.stage_runs:
                duration = None
                if sr.started_at and sr.completed_at:
                    duration = (sr.completed_at - sr.started_at).total_seconds()
                
                stages.append({
                    "stage_name": sr.stage_name,
                    "status": sr.status,
                    "started_at": sr.started_at,
                    "completed_at": sr.completed_at,
                    "duration_seconds": duration
                })
                
        # Build events list
        events = []
        if include_events and workflow.events:
            # Sort events by created_at desc and take top N
            sorted_events = sorted(workflow.events, key=lambda e: e.created_at, reverse=True)
            for event in sorted_events[:events_limit]:
                events.append({
                    "event_type": event.event_type,
                    "event_payload": event.event_payload,
                    "created_at": event.created_at
                })
                
        return {
            "id": workflow.id,
            "temporal_workflow_id": workflow.temporal_workflow_id,
            "workflow_name": workflow.workflow_name,
            "definition_name": workflow.workflow_definition.display_name if workflow.workflow_definition else "Unknown",
            "workflow_type": workflow.workflow_definition.workflow_key if workflow.workflow_definition else "unknown",
            "status": workflow.status,
            "metrics": metrics,
            "created_at": workflow.created_at,
            "updated_at": workflow.updated_at,
            "duration_seconds": self._get_total_duration(workflow),
            "documents": documents,
            "stages": stages,
            "recent_events": events
        }
        
    async def _calculate_workflow_metrics(self, workflow: Any) -> Dict[str, Any]:
        """Calculate document processing metrics for a workflow."""
        total_docs = len(workflow.workflow_documents) if workflow.workflow_documents else 0
        completed_docs = 0
        failed_docs = 0
        processing_docs = 0
        
        if workflow.workflow_documents:
            for wd in workflow.workflow_documents:
                status = wd.document.status
                if status == "extracted":
                    completed_docs += 1
                elif status == "failed":
                    failed_docs += 1
                else:
                    processing_docs += 1
                    
        progress = 0
        if total_docs > 0:
            progress = int((completed_docs / total_docs) * 100)
            
        # Calculate total duration if terminal
        total_duration = self._get_total_duration(workflow)
            
        return {
            "documents_total": total_docs,
            "documents_completed": completed_docs,
            "documents_failed": failed_docs,
            "documents_processing": processing_docs,
            "progress_percent": progress,
            "total_duration_seconds": total_duration
        }

    def _get_total_duration(self, workflow: Any) -> Optional[float]:
        """Calculate total workflow duration in seconds."""
        if not workflow.created_at:
            return None

        # Authoritative source: workflow lifecycle
        if workflow.status in {"completed", "failed"} and workflow.updated_at:
            # If updated_at is very close to created_at but we have stages/events, 
            # it might be stale. Let's find the true end time.
            potential_ends = [workflow.updated_at]
            
            if workflow.stage_runs:
                potential_ends.extend([sr.completed_at for sr in workflow.stage_runs if sr.completed_at])
                potential_ends.extend([sr.started_at for sr in workflow.stage_runs if sr.started_at])
            
            if workflow.events:
                potential_ends.extend([e.created_at for e in workflow.events if e.created_at])
            
            # Use the latest known activity as the end time
            end_time = max(potential_ends)
            duration = (end_time - workflow.created_at).total_seconds()
            return max(duration, 0)

        # Running workflow: created_at -> now (using UTC)
        if workflow.status == "running":
            now = datetime.now(timezone.utc)
            duration = (now - workflow.created_at).total_seconds()
            return max(duration, 0)

        return None

    async def get_workflow_details(self, workflow_id: UUID, user_id: UUID) -> Optional[WorkflowResponse]:
        """Get workflow details.
        
        Args:
            workflow_id: Workflow ID
            user_id: User ID
            
        Returns:
            WorkflowResponse or None
        """
        wf = await self.wf_repo.get_by_id(workflow_id)
        if not wf or wf.user_id != user_id:
            return None
            
        return WorkflowResponse(
            id=wf.id,
            definition_id=wf.workflow_definition_id,
            workflow_name=wf.workflow_name,
            definition_name=wf.workflow_definition.display_name if wf.workflow_definition else "Unknown",
            status=wf.status,
            created_at=wf.created_at,
            updated_at=wf.updated_at,
            duration_seconds=self._get_total_duration(wf)
        )

    async def list_definitions(self) -> List[Dict[str, Any]]:
        """Get all workflow definitions.
        
        Returns:
            List of definitions
        """
        definitions = await self.def_repo.get_all()
        return [
            {
                "id": d.id,
                "key": d.workflow_key,
                "name": d.display_name,
                "description": d.description
            } for d in definitions
        ]

    async def get_all_workflows(
        self, 
        workflow_definition_id: UUID, 
        user_id: UUID, 
        limit: int = 50, 
        offset: int = 0
    ) -> Dict[str, Any]:
        """Get all workflows for a workflow definition with enhanced data.
        
        Args:
            workflow_definition_id: Workflow definition ID
            user_id: User ID
            limit: Max records to return
            offset: Records to skip
            
        Returns:
            Dict containing total count and list of workflows with enhanced data
        """
        filters = {
            "workflow_definition_id": workflow_definition_id,
            "user_id": user_id
        }
        
        # Use existing enhanced fetching logic
        workflows = await self.wf_repo.get_all_with_relationships(
            skip=offset,
            limit=limit,
            filters=filters,
            include_documents=True,
            include_stages=True,
            include_events=True
        )

        total = await self.wf_repo.count(filters=filters)
        
        if not workflows:
            return {
                "total": total,
                "workflows": []
            }
            
        workflow_items = []
        for wf in workflows:
            item = await self._build_workflow_list_item(
                wf, 
                include_documents=True,
                include_stages=True,
                include_events=True
            )
            workflow_items.append(item)
            
        return {
            "total": total,
            "workflows": workflow_items
        }

    async def fetch_definition_by_id(self, definition_id) -> Dict[str, Any]:
        """Get workflow definition by id"""

        definition = await self.def_repo.get_by_definition_id(definition_id)
        return {
            "id": definition.id,
            "key": definition.workflow_key,
            "name": definition.display_name,
            "description": definition.description
        }

    async def get_workflow_extraction(
        self, 
        workflow_id: UUID, 
        document_id: UUID, 
        user_id: UUID
    ) -> Optional[Dict[str, Any]]:
        """Get extracted data for a document in a workflow.
        
        Args:
            workflow_id: Workflow ID
            document_id: Document ID
            user_id: User ID
            
        Returns:
            Extraction data or None if not found/access denied
        """
        wf = await self.wf_repo.get_by_id(workflow_id)
        if not wf or wf.user_id != user_id:
            return None

        extracted_entities = await self.step_entity_output_repo.get_by_document_and_workflow(document_id, workflow_id)
        extracted_section_fields = await self.step_section_output_repo.get_by_document_and_workflow(document_id, workflow_id)
        
        return {
            "workflow_id": workflow_id,
            "document_id": document_id,
            "extracted_data": {
                "sections": [
                    {
                        "section_type": e.section_type,
                        "fields": e.display_payload,
                        "confidence": e.confidence
                    } for e in extracted_section_fields
                ],
                "entities": [
                    {
                        "entity_type": e.entity_type,
                        "fields": e.display_payload,
                        "confidence": e.confidence
                    } for e in extracted_entities
                ]
            }
        }

    async def _create_workflow_logic(
        self,
        workflow_definition_id: UUID,
        user_id: UUID,
        workflow_name: str = "Untitled"
    ) -> Dict[str, Any]:
        """Core logic for creating a draft workflow execution."""
        try:
            workflow_run = await self.wf_repo.create_workflow(
                workflow_definition_id=workflow_definition_id,
                workflow_name=workflow_name,
                status="draft",
                user_id=user_id,
            )
            await self.session.commit()
            
            return {
                "workflow_id": str(workflow_run.id),
                "status": "draft",
                "message": "Draft workflow created successfully."
            }
        except Exception as e:
            self.logger.error(f"Failed to create draft workflow: {e}", exc_info=True)
            await self.session.rollback()
            raise AppError(f"Failed to create draft workflow: {e}", original_error=e)

    async def submit_product_workflow(
        self,
        workflow_name: str,
        workflow_definition_id: str,
        document_ids: List[UUID],
        user_id: UUID,
        metadata: Optional[Dict[str, Any]] = None,
        workflow_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """Submit a product workflow (execution with existing documents).
        
        Args:
            workflow_name: Name of workflow
            workflow_definition_id: ID of definition
            document_ids: List of pre-uploaded document IDs
            user_id: User ID
            metadata: Metadata
            workflow_id: Optional existing workflow ID
            
        Returns:
            Workflow execution result
        """
        # 1. Get definition to verify key
        wf_def = await self.def_repo.get_by_id(UUID(workflow_definition_id))
        if not wf_def:
            raise ValidationError("Workflow definition not found")
            
        # 2. Start workflow
        return await self.execute_workflow(
            workflow_key=wf_def.workflow_key,
            document_ids=document_ids,
            user_id=user_id,
            workflow_name=workflow_name,
            metadata=metadata,
            workflow_id=workflow_id
        )
