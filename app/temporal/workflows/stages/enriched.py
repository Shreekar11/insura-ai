"""EnrichedStageWorkflow - orchestrates all Enriched stage activities."""

from temporalio import workflow
from datetime import timedelta
from typing import Optional, Dict

# Import existing child workflows
from app.temporal.workflows.child.entity_resolution import EntityResolutionWorkflow


@workflow.defn
class EnrichedStageWorkflow:
    """
    Stage workflow for 'Enriched' milestone.
    
    Executes EntityResolution (Canonical resolution + Relationships).
    Automatically marks 'enriched' stage complete.
    """
    
    @workflow.run
    async def run(self, workflow_id: str, document_id: str) -> dict:
        workflow.logger.info(f"Starting EnrichedStage for {document_id}")
        
        # Phase 1: Entity Resolution & Relationships
        enrichment_result = await workflow.execute_child_workflow(
            EntityResolutionWorkflow.run,
            args=[workflow_id, document_id],
            id=f"stage-enriched-resolution-{document_id}",
            task_queue="documents-queue",
        )
        
        # Mark enriched stage complete
        await workflow.execute_activity(
            "update_stage_status",
            args=[workflow_id, document_id, "enriched", "completed"],
            start_to_close_timeout=timedelta(seconds=30),
        )
        
        return {
            "stage": "enriched",
            "status": "completed",
            "workflow_id": workflow_id,
            "document_id": document_id,
            "entities_resolved": enrichment_result.get("resolved_count", 0),
            "relationships_extracted": enrichment_result.get("relationship_count", 0),
        }
