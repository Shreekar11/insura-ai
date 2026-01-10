"""ProcessedStageWorkflow - orchestrates all Processed stage activities."""

from temporalio import workflow
from datetime import timedelta
from typing import Optional, Dict

# Import existing child workflows
from app.temporal.workflows.child.page_analysis import PageAnalysisWorkflow
from app.temporal.workflows.child.ocr_extraction import OCRExtractionWorkflow
from app.temporal.workflows.child.table_extraction import TableExtractionWorkflow
from app.temporal.workflows.child.hybrid_chunking import HybridChunkingWorkflow


@workflow.defn
class ProcessedStageWorkflow:
    """
    Stage workflow for 'Processed' milestone.
    
    Executes PageAnalysis (which includes classification), OCR, Tables, Chunking.
    Automatically marks both 'processed' and 'classified' stages complete.
    """
    
    @workflow.run
    async def run(self, workflow_id: str, document_id: str) -> dict:
        workflow.logger.info(f"Starting ProcessedStage for {document_id}", extra={"workflow_id": workflow_id})

        # Initialize processed and classified stages as running
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
        
        # Phase 1: OCR Extraction
        ocr_result = await workflow.execute_child_workflow(
            OCRExtractionWorkflow.run,
            args=[workflow_id, document_id], 
            id=f"stage-processed-ocr-{document_id}",
            task_queue="documents-queue",
        )
        
        # Extract markdown pages from OCR result
        markdown_pages = ocr_result.get("markdown_pages", [])
        
        # Phase 2: Page Analysis
        page_manifest = await workflow.execute_child_workflow(
            PageAnalysisWorkflow.run,
            args=[document_id, markdown_pages, workflow_id],
            id=f"stage-processed-page-analysis-{document_id}",
            task_queue="documents-queue",
        )
        
        document_profile = page_manifest.get('document_profile', {})
        page_section_map = page_manifest.get('page_section_map')
        pages_to_process = page_manifest.get('pages_to_process', [])
        
        # Phase 3: Table Extraction
        table_result = await workflow.execute_child_workflow(
            TableExtractionWorkflow.run,
            args=[workflow_id, document_id, pages_to_process],
            id=f"stage-processed-table-{document_id}",
            task_queue="documents-queue",
        )
        
        # Phase 4: Hybrid Chunking
        chunking_result = await workflow.execute_child_workflow(
            HybridChunkingWorkflow.run,
            args=[workflow_id, document_id, page_section_map],
            id=f"stage-processed-chunking-{document_id}",
            task_queue="documents-queue",
        )
        
        # Mark processed and classified stages complete
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
