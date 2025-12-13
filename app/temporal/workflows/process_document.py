"""Parent workflow orchestrating the entire document processing pipeline.

This workflow coordinates the execution of child workflows for:
0. Page Analysis (determines which pages to process)
1. OCR Extraction (only on filtered pages)
2. Normalization (includes classification and entity extraction)
3. Entity Resolution (includes relationship extraction)

All child workflows execute on the same task queue: documents-queue
"""

from temporalio import workflow
from datetime import timedelta
from typing import Optional

from .page_analysis_workflow import PageAnalysisWorkflow
from .ocr_extraction import OCRExtractionWorkflow
from .normalization import NormalizationWorkflow
from .entity_resolution import EntityResolutionWorkflow


@workflow.defn
class ProcessDocumentWorkflow:
    """
    Parent workflow orchestrating entire document processing pipeline.
    All child workflows execute on the same task queue.
    """
    
    def __init__(self):
        self._status = "initialized"
        self._current_phase: Optional[str] = None
        self._progress = 0.0
    
    @workflow.query
    def get_status(self) -> dict:
        """Query handler for real-time status updates."""
        return {
            "status": self._status,
            "current_phase": self._current_phase,
            "progress": self._progress,
        }
    
    @workflow.run
    async def run(self, document_id: str) -> dict:
        """
        Execute the complete document processing pipeline.
        
        Args:
            document_id: UUID of the document to process
            
        Returns:
            Dictionary with processing results and statistics
        """
        workflow.logger.info(f"Starting document processing: {document_id}")
        self._status = "processing"
        
        # Phase 0: Page Analysis
        # Analyzes all pages and creates manifest of which pages to process
        self._current_phase = "page_analysis"
        self._progress = 0.05
        page_manifest = await workflow.execute_child_workflow(
            PageAnalysisWorkflow.run,
            document_id,
            id=f"page-analysis-{document_id}",
            task_queue="documents-queue",
        )
        workflow.logger.info(
            f"Page analysis complete: {page_manifest['total_pages']} pages, "
            f"{len(page_manifest['pages_to_process'])} to process "
            f"({page_manifest['processing_ratio']:.1%})"
        )
        
        # Phase 1: OCR Extraction
        # Only OCRs pages marked as should_process in the manifest
        self._current_phase = "ocr_extraction"
        self._progress = 0.15
        ocr_result = await workflow.execute_child_workflow(
            OCRExtractionWorkflow.run,
            args=[document_id, page_manifest['pages_to_process']],
            id=f"ocr-{document_id}",
            task_queue="documents-queue",
        )
        workflow.logger.info(
            f"OCR complete: {ocr_result.get('page_count', 0)} pages extracted "
            f"(processed {len(page_manifest['pages_to_process'])} of {page_manifest['total_pages']} pages)"
        )
        
        # Phase 2: Normalization
        # This includes chunking, classification, and entity extraction
        self._current_phase = "normalization"
        self._progress = 0.4
        norm_result = await workflow.execute_child_workflow(
            NormalizationWorkflow.run,
            document_id,
            id=f"norm-{document_id}",
            task_queue="documents-queue",
        )
        workflow.logger.info(
            f"Normalization complete: {norm_result['chunk_count']} chunks, "
            f"{norm_result['entity_count']} entities, "
            f"{len(norm_result.get('section_types', {}))} section types detected"
        )
        
        # Phase 3: Entity Resolution
        # This includes canonical resolution and relationship extraction
        self._current_phase = "entity_resolution"
        self._progress = 0.7
        entity_result = await workflow.execute_child_workflow(
            EntityResolutionWorkflow.run,
            document_id,
            id=f"entity-{document_id}",
            task_queue="documents-queue",
        )
        workflow.logger.info(
            f"Entities resolved: {entity_result['entity_count']} entities, "
            f"{entity_result['relationship_count']} relationships"
        )
        
        # Phase 4: Graph Construction - SKIPPED (Future Implementation)
        # TODO: Add GraphConstructionWorkflow in future phase after vector indexing is implemented
        # self._current_phase = "graph_construction"
        # self._progress = 0.9
        
        # Complete
        self._status = "completed"
        self._progress = 1.0
        
        return {
            "status": "completed",
            "document_id": document_id,
            "total_pages": page_manifest['total_pages'],
            "pages_processed": len(page_manifest['pages_to_process']),
            "pages_skipped": len(page_manifest['pages_skipped']),
            "processing_ratio": page_manifest['processing_ratio'],
            "page_count": ocr_result.get('page_count', 0),
            "chunks": norm_result['chunk_count'],
            "entities": entity_result['entity_count'],
            "relationships": entity_result['relationship_count'],
            "classification": norm_result.get('classification', {}),
            "section_types": norm_result.get('section_types', {}),
        }
