"""Parent workflow orchestrating the entire document processing pipeline."""

from temporalio import workflow
from datetime import timedelta
from typing import Optional, Dict

# Import shared stage workflows
from app.temporal.shared.workflows.stages.processed import ProcessedStageWorkflow
from app.temporal.shared.workflows.stages.extracted import ExtractedStageWorkflow
from app.temporal.shared.workflows.stages.enriched import EnrichedStageWorkflow
from app.temporal.shared.workflows.stages.summarized import SummarizedStageWorkflow

from app.temporal.core.workflow_registry import WorkflowRegistry, WorkflowType


@WorkflowRegistry.register(category=WorkflowType.SHARED)
@workflow.defn
class ProcessDocumentWorkflow:
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

        # Stage 1: Processed
        self._progress = 0.0
        self._current_phase = "processed"
        processed_result = await workflow.execute_child_workflow(
            ProcessedStageWorkflow.run,
            args=[workflow_id, document_id],
            id=f"gate-processed-{document_id}",
        )
        document_profile = processed_result.get("document_profile")

        self._progress = 0.2
        self._current_phase = "classified"

        # Stage 2: Extracted
        self._progress = 0.4
        self._current_phase = "extracted"
        await workflow.execute_activity(
            "update_stage_status",
            args=[workflow_id, document_id, "extracted", "running"],
            start_to_close_timeout=timedelta(seconds=30),
        )
        extracted_result = await workflow.execute_child_workflow(
            ExtractedStageWorkflow.run,
            args=[workflow_id, document_id, document_profile],
            id=f"gate-extracted-{document_id}",
        )
        await workflow.execute_activity(
            "update_stage_status",
            args=[workflow_id, document_id, "extracted", "completed"],
            start_to_close_timeout=timedelta(seconds=30),
        )

        # Stage 3: Enriched
        self._progress = 0.6
        self._current_phase = "enriched"
        await workflow.execute_activity(
            "update_stage_status",
            args=[workflow_id, document_id, "enriched", "running"],
            start_to_close_timeout=timedelta(seconds=30),
        )
        await workflow.execute_child_workflow(
            EnrichedStageWorkflow.run,
            args=[workflow_id, document_id],
            id=f"gate-enriched-{document_id}",
        )
        await workflow.execute_activity(
            "update_stage_status",
            args=[workflow_id, document_id, "enriched", "completed"],
            start_to_close_timeout=timedelta(seconds=30),
        )

        # Stage 4: Summarized
        self._progress = 0.8
        self._current_phase = "summarized"
        await workflow.execute_activity(
            "update_stage_status",
            args=[workflow_id, document_id, "summarized", "running"],
            start_to_close_timeout=timedelta(seconds=30),
        )
        summarized_result = await workflow.execute_child_workflow(
            SummarizedStageWorkflow.run,
            args=[workflow_id, document_id],
            id=f"gate-summarized-{document_id}",
        )
        await workflow.execute_activity(
            "update_stage_status",
            args=[workflow_id, document_id, "summarized", "completed"],
            start_to_close_timeout=timedelta(seconds=30),
        )

        self._status = "completed"
        self._progress = 1.0

        return {
            "status": self._status,
            "workflow_id": workflow_id,
            "document_id": document_id,
            "document_type": processed_result.get("document_type"),
            "stages": {
                "processed": processed_result,
                "extracted": extracted_result,
                "enriched": {}, # enrichment_result had different keys than enrichment_result in summarized stage etc.
                "summarized": summarized_result,
            }
        }
