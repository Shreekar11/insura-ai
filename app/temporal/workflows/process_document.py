"""Parent workflow orchestrating the entire document processing pipeline.

This workflow coordinates the execution of child workflows within the stage workflows:

Stage workflows:
0. Processed Stage Workflow
    - Page Analysis (determines which pages to process + builds document profile)
    - OCR Extraction (only on filtered pages, with page_type metadata)
    - Table Extraction (extracts tables from pages with has_tables flag)
    - Hybrid Chunking (uses page_section_map from manifest)
1. Classified Stage Workflow
    - Page Classifier from Page Analysis workflow
    - Uses document_profile from manifest to classify document
2. Extracted Stage Workflow
    - Extracts section fields and entities using LLM
3. Enriched Stage Workflow
    - Normalizes entities in canonical form and creates relationships
4. Summarized Stage Workflow
    - Generates document summary using LLM
    - Vector embeddings and knowledge graph generation

All child workflows execute on the same task queue: documents-queue
"""

from temporalio import workflow
from datetime import timedelta
from typing import Optional, Dict

from .stages.processed import ProcessedStageWorkflow
from .stages.classified import ClassifiedStageWorkflow
from .stages.extracted import ExtractedStageWorkflow
from .stages.enriched import EnrichedStageWorkflow
from .stages.summarized import SummarizedStageWorkflow


@workflow.defn
class ProcessDocumentWorkflow:
    """
    Parent workflow orchestrating entire document processing pipeline.
    
    The manifest from Phase 0 is passed to all downstream workflows:
    - OCR: receives page_section_map to store page_type metadata
    - Chunking: receives page_section_map for section assignment
    - Extraction: receives document_profile to skip Tier 1 LLM
    
    All child workflows execute on the same task queue.
    """
    
    def __init__(self):
        self._status = "initialized"
        self._current_phase: Optional[str] = None
        self._progress = 0.0
        self._document_profile: Optional[Dict] = None
    
    @workflow.query
    def get_status(self) -> dict:
        """Query handler for real-time status updates."""
        return {
            "status": self._status,
            "current_phase": self._current_phase,
            "progress": self._progress,
            "document_type": (
                self._document_profile.get("document_type") 
                if self._document_profile else None
            ),
        }
    
    @workflow.run
    async def run(self, document_id: str) -> dict:
        """
        Execute the complete document processing pipeline.
        
        Args:
            document_id: UUID of the document to process
            
        Returns:
            Dictionary with processing results and stage completion info
        """
        workflow.logger.info(f"Starting document processing: {document_id}")
        self._status = "processing"

        # Stage 1: Processed (Page Analysis + OCR + Chunking)
        self._current_phase = "processed"
        self._progress = 0.0

        processed_result = await workflow.execute_child_workflow(
            ProcessDocumentWorkflow.run,
            document_id,
            id=f"gate-processed-{document_id}",
            task_queue="documents-queue",
        )

        self._progress = 0.2
        self._current_phase = "classified"

        # Stage 2: Extracted (Section fields + Entities)
        self._progress = 0.4
        self._current_phase = "extracted"
        extracted_result = await workflow.execute_child_workflow(
            ExtractedStageWorkflow.run,
            document_id,
            id=f"gate-extracted-{document_id}",
            task_queue="documents-queue",
        )

        # Stage 3: Enriched (Canonical resolution + Relationships)
        self._progress = 0.6
        self._current_phase = "enriched"
        enriched_result = await workflow.execute_child_workflow(
            EnrichedStageWorkflow.run,
            document_id,
            id=f"gate-enriched-{document_id}",
            task_queue="documents-queue",
        )

        # Stage 4: Summarized (Summaries + Embeddings)
        self._progress = 0.8
        self._current_phase = "summarized"
        summarized_result = await workflow.execute_child_workflow(
            SummarizedStageWorkflow.run,
            document_id,
            id=f"gate-summarized-{document_id}",
            task_queue="documents-queue",
        )

        # Complete
        self._status = "completed"
        self._progress = 1.0

        return {
            "status": self._status,
            "document_id": document_id,
            "document_type": processed_result.get("document_type"),
            "stages": {
                "processed": processed_result,
                "extracted": extracted_result,
                "enriched": enriched_result,
                "summarized": summarized_result,
            }
        }   

