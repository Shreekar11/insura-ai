"""Parent workflow orchestrating the entire document processing pipeline."""

from temporalio import workflow
from datetime import timedelta
from typing import Optional, Dict

from app.temporal.shared.workflows.mixin import DocumentProcessingMixin, DocumentProcessingConfig
from app.temporal.core.workflow_registry import WorkflowRegistry, WorkflowType


@WorkflowRegistry.register(category=WorkflowType.SHARED)
@workflow.defn
class ProcessDocumentWorkflow(DocumentProcessingMixin):
    """Parent workflow orchestrating entire document processing pipeline."""
    
    def __init__(self):
        self._status = "initialized"
        self._current_phase: Optional[str] = None
        self._progress = 0.0
        self._document_profile: Optional[Dict] = None
    
    @workflow.query
    def get_status(self) -> dict:
        """Query handler for real-time status updates."""
        return {
            "status": self._status,
            "current_phase": self._current_phase,
            "progress": self._progress,
            "document_type": (
                self._document_profile.get("document_type") 
                if self._document_profile else None
            ),
        }
    
    @workflow.run
    async def run(self, payload: Dict) -> dict:
        """Execute the complete document processing pipeline."""
        workflow_id = payload.get("workflow_id")
        documents = payload.get("documents")

        if len(documents) != 1:
            raise ValueError("ProcessDocumentWorkflow requires exactly one document")

        document_id = documents[0].get("document_id")
        self._status = "processing"

        config = DocumentProcessingConfig(
            workflow_id=workflow_id,
            workflow_name=payload.get("workflow_name")
        )
        
        # Execute the processing stages via mixin
        results = await self.process_document(document_id, config)
        
        self._status = "completed"
        self._progress = 1.0

        # Persist status to database
        await workflow.execute_activity(
            "update_workflow_status",
            args=[workflow_id, "completed"],
            start_to_close_timeout=timedelta(minutes=1),
        )

        return {
            "status": self._status,
            "workflow_id": workflow_id,
            "document_id": document_id,
            "document_type": results.get("processed", {}).get("document_type"),
            "stages": {
                "processed": results.get("processed"),
                "extracted": results.get("extracted"),
                "enriched": results.get("enriched"),
                "summarized": results.get("summarized"),
            }
        }
