"""EnrichedStageWorkflow - orchestrates all Enriched stage activities."""

from temporalio import workflow
from datetime import timedelta
from typing import Optional, Dict

# Import child workflows from shared namespace
from app.temporal.shared.workflows.child.entity_resolution import EntityResolutionWorkflow

from app.temporal.core.workflow_registry import WorkflowRegistry, WorkflowType


@WorkflowRegistry.register(category=WorkflowType.SHARED)
@workflow.defn
class EnrichedStageWorkflow:
    """Stage workflow for 'Enriched' milestone."""
    
    @workflow.run
    async def run(self, workflow_id: str, document_id: str) -> dict:
        workflow.logger.info(f"Starting EnrichedStage for {document_id}")
        
        enrichment_result = await workflow.execute_child_workflow(
            EntityResolutionWorkflow.run,
            args=[workflow_id, document_id],
            id=f"stage-enriched-resolution-{document_id}",
        )
        
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
