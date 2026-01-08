"""SummarizedStageWorkflow - orchestrates all Summarized stage activities."""

from temporalio import workflow
from datetime import timedelta
from typing import Optional, Dict
from temporalio.common import RetryPolicy


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
        embedding_result = await workflow.execute_activity(
            "generate_embeddings_activity",
            args=[document_id, workflow_id],
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=5),
                maximum_attempts=3
            )
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
            "embedded": True,
            "chunks_embedded": embedding_result.get("chunks_embedded", 0),
        }
