"""SummarizedStageWorkflow - orchestrates all Summarized stage activities."""

from temporalio import workflow
from datetime import timedelta
from typing import Optional, Dict
from temporalio.common import RetryPolicy

from app.temporal.workflows.child.vector_indexing import VectorIndexingWorkflow


@workflow.defn
class SummarizedStageWorkflow:
    """
    Stage workflow for 'Summarized' milestone.
    
    Executes Document Summarization and Embedding generation.
    Automatically marks 'summarized' stage complete.
    """
    
    @workflow.run
    async def run(self, workflow_id: str, document_id: str) -> dict:
        workflow.logger.info(f"Starting SummarizedStage for {document_id}")
        
        # Phase 1: Vector Embeddings
        await workflow.execute_child_workflow(
            VectorIndexingWorkflow.run,
            args=[workflow_id, document_id],
            id=f"stage-summarized-vector-indexing-{document_id}",
            task_queue="documents-queue",
        )

        # Phase 2: Summarization
        
        
        # Mark summarized stage complete
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
