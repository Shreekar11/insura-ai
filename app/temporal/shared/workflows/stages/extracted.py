"""ExtractedStageWorkflow - orchestrates all Extracted stage activities."""

from temporalio import workflow
from datetime import timedelta
from typing import Any, Dict, Optional

# Import child workflows from shared namespace
from app.temporal.shared.workflows.child.extraction import ExtractionWorkflow

from app.temporal.core.workflow_registry import WorkflowRegistry, WorkflowType


@WorkflowRegistry.register(category=WorkflowType.SHARED)
@workflow.defn
class ExtractedStageWorkflow:
    """Stage workflow for 'Extracted' milestone."""
    
    @workflow.run
    async def run(
        self, 
        workflow_id: str,
        document_id: str,
        document_profile: Dict[str, Any],
        target_sections: Optional[list[str]] = None,
        target_entities: Optional[list[str]] = None,
    ) -> dict:
        workflow.logger.info(f"Starting ExtractedStage for {document_id}")
        
        extraction_result = await workflow.execute_child_workflow(
            ExtractionWorkflow.run,
            args=[workflow_id, document_id, document_profile, target_sections, target_entities],
            id=f"stage-extracted-{document_id}",
        )
        
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
