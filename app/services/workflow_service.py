"""Workflow service for orchestrating document processing pipelines."""

from uuid import UUID
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.document_repository import DocumentRepository
from app.repositories.workflow_repository import (
    WorkflowRepository,
    WorkflowDefinitionRepository,
    WorkflowDocumentRepository,
)
from app.repositories.stages_repository import StagesRepository
from app.core.temporal_client import get_temporal_client
from app.temporal.shared.workflows.process_document import ProcessDocumentWorkflow
from app.utils.logging import get_logger
from app.services.base_service import BaseService
from app.core.exceptions import ValidationError, AppError

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
                kwargs.get("metadata")
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
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute a generic workflow by its key.
        
        Args:
            workflow_key: Key of the workflow definition to execute
            document_ids: List of document IDs involved
            user_id: ID of the user initiating the workflow
            metadata: Optional metadata for the workflow
            
        Returns:
            Dict containing workflow details and status
        """
        return await self.execute(
            action="execute_workflow",
            workflow_key=workflow_key,
            document_ids=document_ids,
            user_id=user_id,
            metadata=metadata
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

    async def _execute_generic_workflow(
        self,
        workflow_key: str,
        document_ids: List[UUID],
        user_id: UUID,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Core logic for executing a generic workflow.
        
        Args:
            workflow_key: Key of the workflow definition
            document_ids: List of document IDs
            user_id: User ID
            metadata: Optional metadata
            
        Returns:
            Dict containing workflow details and status
        """
        try:
            # Step 1: Get workflow definition
            definition = await self.def_repo.get_by_key(workflow_key)
            if not definition:
                raise ValidationError(f"Workflow definition {workflow_key} not found")

            # Step 2: Create workflow execution record
            self.logger.info(f"Creating workflow run for generic workflow: {workflow_key}")
            workflow_run = await self.wf_repo.create_workflow(
                workflow_definition_id=definition.id,
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
                
                await self.wf_doc_repo.create_workflow_document(
                    workflow_id=workflow_id,
                    document_id=doc_id,
                )
                documents_data.append({
                    "document_id": str(doc_id),
                    "url": doc.file_path
                })

            # Commit database changes before Temporal
            await self.session.commit()

            # Step 4: Start Temporal workflow
            self.logger.info(f"Starting Temporal workflow for {workflow_key}: {workflow_id}")
            temporal_client = await get_temporal_client()
            
            # Map workflow key to workflow class
            from app.temporal.workflows.policy_comparison import PolicyComparisonWorkflow
            workflow_class_map = {
                "policy_comparison": PolicyComparisonWorkflow,
                # Add more mappings as needed
            }
            
            wf_class = workflow_class_map.get(workflow_key)
            if not wf_class:
                raise ValidationError(f"Temporal workflow not implemented for key: {workflow_key}")

            workflow_handle = await temporal_client.start_workflow(
                wf_class.run,
                {
                    "workflow_id": str(workflow_id),
                    "workflow_definition_id": str(definition.id),
                    "documents": documents_data,
                    "metadata": metadata or {},
                },
                id=f"workflow-{workflow_id}",
                task_queue="documents-queue",
            )

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
