"""ExtractedStageWorkflow - orchestrates all Extracted stage activities."""

from temporalio import workflow
from datetime import timedelta
from typing import Any, Dict

# Import existing child workflows
from app.temporal.workflows.child.extraction import ExtractionWorkflow


@workflow.defn
class ExtractedStageWorkflow:
    """
    Stage workflow for 'Extracted' milestone.
    
    Executes Extraction (Section fields + Entity extraction).
    Automatically marks 'extracted' stage complete.
    """
    
    @workflow.run
    async def run(
        self, 
        workflow_id: str,
        document_id: str,
        document_profile: Dict[str, Any],
    ) -> dict:
        workflow.logger.info(f"Starting ExtractedStage for {document_id}")
        
        # Phase 1: Extraction (Sections + Entities)
        extraction_result = await workflow.execute_child_workflow(
            ExtractionWorkflow.run,
            args=[workflow_id, document_id, document_profile],
            id=f"stage-extracted-{document_id}",
            task_queue="documents-queue",
        )
        
        # Mark extracted stage complete
        await workflow.execute_activity(
            "update_stage_status",
            args=[workflow_id, document_id, "extracted", "completed"],
            start_to_close_timeout=timedelta(seconds=30),
        )
        
        return {
            "stage": "extracted",
            "status": "completed",
            "workflow_id": workflow_id,
            "document_id": document_id,
            "sections_extracted": len(extraction_result.get("sections", [])),
            "entities_found": extraction_result.get("entity_count", 0),
        }
