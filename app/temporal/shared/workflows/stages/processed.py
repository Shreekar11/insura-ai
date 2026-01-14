"""ProcessedStageWorkflow - orchestrates all Processed stage activities."""

from temporalio import workflow
from datetime import timedelta
from typing import Optional, Dict, List

# Import child workflows from shared namespace
from app.temporal.shared.workflows.child.page_analysis import PageAnalysisWorkflow
from app.temporal.shared.workflows.child.ocr_extraction import OCRExtractionWorkflow
from app.temporal.shared.workflows.child.table_extraction import TableExtractionWorkflow
from app.temporal.shared.workflows.child.hybrid_chunking import HybridChunkingWorkflow

from app.temporal.core.workflow_registry import WorkflowRegistry, WorkflowType


@WorkflowRegistry.register(category=WorkflowType.SHARED)
@workflow.defn
class ProcessedStageWorkflow:
    """Stage workflow for 'Processed' milestone."""
    
    @workflow.run
    async def run(
        self, 
        workflow_id: str, 
        document_id: str,
        ensure_table_extraction: bool = True,
        target_sections: Optional[List[str]] = None
    ) -> dict:
        workflow.logger.info(f"Starting ProcessedStage for {document_id}")

        await workflow.execute_activity(
            "update_stage_status",
            args=[workflow_id, document_id, "processed", "running"],
            start_to_close_timeout=timedelta(seconds=30),
        )
        await workflow.execute_activity(
            "update_stage_status",
            args=[workflow_id, document_id, "classified", "running"],
            start_to_close_timeout=timedelta(seconds=30),
        )
        
        ocr_result = await workflow.execute_child_workflow(
            OCRExtractionWorkflow.run,
            args=[workflow_id, document_id], 
            id=f"stage-processed-ocr-{document_id}",
        )
        
        markdown_pages = ocr_result.get("markdown_pages", [])
        
        page_manifest = await workflow.execute_child_workflow(
            PageAnalysisWorkflow.run,
            args=[document_id, markdown_pages, workflow_id],
            id=f"stage-processed-page-analysis-{document_id}",
        )
        
        document_profile = page_manifest.get('document_profile', {})
        page_section_map = page_manifest.get('page_section_map')
        pages_to_process = page_manifest.get('pages_to_process', [])
        
        if ensure_table_extraction:
            table_result = await workflow.execute_child_workflow(
                TableExtractionWorkflow.run,
                args=[workflow_id, document_id, pages_to_process],
                id=f"stage-processed-table-{document_id}",
            )
        else:
            table_result = {"tables_found": 0}
        
        section_boundaries = document_profile.get('section_boundaries', [])
        
        chunking_result = await workflow.execute_child_workflow(
            HybridChunkingWorkflow.run,
            args=[workflow_id, document_id, page_section_map, target_sections, section_boundaries],
            id=f"stage-processed-chunking-{document_id}",
        )
        
        await workflow.execute_activity(
            "update_stage_status",
            args=[workflow_id, document_id, "processed", "completed"],
            start_to_close_timeout=timedelta(seconds=30),
        )
        await workflow.execute_activity(
            "update_stage_status",
            args=[workflow_id, document_id, "classified", "completed"],
            start_to_close_timeout=timedelta(seconds=30),
        )
        
        return {
            "stage": "processed",
            "status": "completed",
            "workflow_id": workflow_id,
            "document_id": document_id,
            "document_type": document_profile.get("document_type"),
            "pages_processed": len(pages_to_process),
            "tables_found": table_result.get("tables_found", 0),
            "chunks_created": chunking_result.get("chunk_count", 0),
            "document_profile": document_profile,
            "classified": True,
        }
