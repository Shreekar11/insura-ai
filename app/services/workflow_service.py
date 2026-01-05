"""Workflow service for orchestrating document processing pipelines."""

import uuid
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.document_repository import DocumentRepository
from app.repositories.workflow_repository import (
    WorkflowRepository,
    WorkflowDefinitionRepository,
    WorkflowDocumentRepository,
)
from app.repositories.stages_repository import StagesRepository
from app.temporal_client import get_temporal_client
from app.temporal.workflows.process_document import ProcessDocumentWorkflow
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)

class WorkflowService:
    """Service for managing document processing workflows.
    
    Coordinates between database repositories and Temporal client.
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.doc_repo = DocumentRepository(session)
        self.wf_repo = WorkflowRepository(session)
        self.wf_doc_repo = WorkflowDocumentRepository(session)
        self.def_repo = WorkflowDefinitionRepository(session)
        self.stage_repo = StagesRepository(session)

    async def start_extraction_workflow(self, pdf_url: str, user_id: uuid.UUID) -> Dict[str, Any]:
        """Orchestrates the start of a document extraction workflow.
        
        1. Ensures workflow definition exists.
        2. Creates workflow execution record.
        3. Creates document record.
        4. Links document to workflow.
        5. Starts Temporal workflow.
        6. Persists Temporal ID.
        """
        try:
            # Step 1: Ensure workflow definition exists
            workflow_key = "document_extraction"
            definition = await self.def_repo.get_by_key(workflow_key)
            if not definition:
                definition = await self.def_repo.create(
                    workflow_key=workflow_key,
                    display_name="Document Extraction",
                    description="OCR, classification, section extraction, and enrichment",
                    supports_multi_docs=False,
                )

            # Step 2: Create workflow execution
            workflow_run = await self.wf_repo.create_workflow(
                workflow_definition_id=definition.id,
                status="running",
            )
            workflow_id = workflow_run.id

            # Step 3: Create document record
            document = await self.doc_repo.create_document(
                file_path=pdf_url,
                page_count=0,
                user_id=user_id,
            )
            document_id = document.id

            # Step 4: Link document to workflow
            await self.wf_doc_repo.create_workflow_document(
                workflow_id=workflow_id,
                document_id=document_id,
            )

            # Commit database changes before interacting with Temporal
            await self.session.commit()

            # Step 5: Start Temporal workflow
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
            await self.wf_repo.update_temporal_id(
                workflow_id=workflow_id,
                temporal_workflow_id=workflow_handle.id,
            )
            await self.session.commit()

            return {
                "workflow_id": str(workflow_id),
                "documents": [str(document_id)],
                "temporal_id": workflow_handle.id,
                "status": "processing",
                "message": "Document extraction workflow started.",
            }

        except Exception as e:
            LOGGER.error(f"Workflow service failed to start extraction: {str(e)}", exc_info=True)
            await self.session.rollback()
            raise

    async def get_workflow_status(self, workflow_id: str) -> Dict[str, Any]:
        """Queries Temporal for the current workflow status."""
        try:
            temporal_client = await get_temporal_client()
            handle = temporal_client.get_workflow_handle(workflow_id)
            status_data = await handle.query("get_status")
            
            return {
                "workflow_id": workflow_id,
                "status": status_data.get("status", "unknown"),
                "current_phase": status_data.get("current_phase"),
                "progress": status_data.get("progress", 0.0),
            }
        except Exception as e:
            LOGGER.error(f"Failed to query workflow status for {workflow_id}: {str(e)}", exc_info=True)
            raise

    async def get_all_document_stages(self) -> List[Any]:
        """Get the completion status of all processing stages for all documents."""
        return await self.stage_repo.get_all_document_stages()

    async def get_document_stage(self, document_id: uuid.UUID, workflow_id: Optional[uuid.UUID] = None) -> List[Any]:
        """Get the completion status of all processing stages for a document."""
        return await self.stage_repo.get_document_stage(document_id, workflow_id)
