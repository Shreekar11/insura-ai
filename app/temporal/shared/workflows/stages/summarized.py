"""SummarizedStageWorkflow - orchestrates all Summarized stage activities."""

from temporalio import workflow
from datetime import timedelta
from typing import Optional, Dict
from temporalio.common import RetryPolicy

# Import child workflows from shared namespace
from app.temporal.shared.workflows.child.indexing import IndexingWorkflow

from app.temporal.core.workflow_registry import WorkflowRegistry, WorkflowType


@WorkflowRegistry.register(category=WorkflowType.SHARED)
@workflow.defn
class SummarizedStageWorkflow:
    """Stage workflow for 'Summarized' milestone."""
    
    @workflow.run
    async def run(
        self, 
        workflow_id: str, 
        document_id: str,
        target_sections: Optional[list[str]] = None
    ) -> dict:
        workflow.logger.info(f"Starting SummarizedStage for {document_id}")
        
        await workflow.execute_child_workflow(
            IndexingWorkflow.run,
            args=[workflow_id, document_id, target_sections],
            id=f"stage-summarized-indexing-{document_id}",
        )

        await workflow.execute_activity(
            "update_stage_status",
            args=[workflow_id, document_id, "summarized", "completed"],
            start_to_close_timeout=timedelta(seconds=30),
        )
        
        return {
            "stage": "summarized",
            "status": "completed",
            "document_id": document_id,
            "summarized": True,
            "indexed": True,
        }
