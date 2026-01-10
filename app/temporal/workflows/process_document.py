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
    - Extraction: receives document_profile for section field and entity extraction
    
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
    async def run(self, payload: Dict) -> dict:
        """
        Execute the complete document processing pipeline.
        
        Args:
            payload: Dictionary containing:
                - workflow_id: UUID of the workflow to process
                - documents: List of dictionaries containing:
                    - document_id: UUID of the document to process
                    - url: URL of the document to process
            
        Returns:
            Dictionary with processing results and stage completion info
        """

        workflow_id = payload.get("workflow_id")
        documents = payload.get("documents")

        # For ProcessDocumentWorkflow, we only reqiure a single document
        if len(documents) != 1:
            raise ValueError("ProcessDocumentWorkflow requires exactly one document")

        document_id = documents[0].get("document_id")

        workflow.logger.info(f"Starting document processing: {document_id}")
        self._status = "processing"

        # Stage 1: Processed (OCR + Page Analysis + Table Extraction + Hybrid Chunking)
        self._progress = 0.0
        self._current_phase = "processed"

        processed_result = await workflow.execute_child_workflow(
            ProcessedStageWorkflow.run,
            args=[workflow_id, document_id],
            id=f"gate-processed-{document_id}",
            task_queue="documents-queue",
        )

        document_profile = processed_result.get("document_profile")

        self._progress = 0.2
        self._current_phase = "classified"

        # Stage 2: Extracted (Section fields + Entities Extraction)
        self._progress = 0.4
        self._current_phase = "extracted"

        await workflow.execute_activity(
            "update_stage_status",
            args=[workflow_id, document_id, "extracted", "running"],
            start_to_close_timeout=timedelta(seconds=30),
        )

        extracted_result = await workflow.execute_child_workflow(
            ExtractedStageWorkflow.run,
            args=[workflow_id, document_id, document_profile],
            id=f"gate-extracted-{document_id}",
            task_queue="documents-queue",
        )

        await workflow.execute_activity(
            "update_stage_status",
            args=[workflow_id, document_id, "extracted", "completed"],
            start_to_close_timeout=timedelta(seconds=30),
        )

        # Stage 3: Enriched (Canonical Resolution + Relationships Extraction)
        self._progress = 0.6
        self._current_phase = "enriched"

        await workflow.execute_activity(
            "update_stage_status",
            args=[workflow_id, document_id, "enriched", "running"],
            start_to_close_timeout=timedelta(seconds=30),
        )

        enriched_result = await workflow.execute_child_workflow(
            EnrichedStageWorkflow.run,
            args=[workflow_id, document_id],
            id=f"gate-enriched-{document_id}",
            task_queue="documents-queue",
        )

        await workflow.execute_activity(
            "update_stage_status",
            args=[workflow_id, document_id, "enriched", "completed"],
            start_to_close_timeout=timedelta(seconds=30),
        )

        # Stage 4: Summarized (Vector Indexing + Knowledge Graph Construction + Workflow summary)
        self._progress = 0.8
        self._current_phase = "summarized"
        await workflow.execute_activity(
            "update_stage_status",
            args=[workflow_id, document_id, "summarized", "running"],
            start_to_close_timeout=timedelta(seconds=30),
        )

        summarized_result = await workflow.execute_child_workflow(
            SummarizedStageWorkflow.run,
            args=[workflow_id, document_id],
            id=f"gate-summarized-{document_id}",
            task_queue="documents-queue",
        )

        await workflow.execute_activity(
            "update_stage_status",
            args=[workflow_id, document_id, "summarized", "completed"],
            start_to_close_timeout=timedelta(seconds=30),
        )

        # Complete
        self._status = "completed"
        self._progress = 1.0

        return {
            "status": self._status,
            "workflow_id": workflow_id,
            "document_id": document_id,
            "document_type": processed_result.get("document_type"),
            "stages": {
                "processed": processed_result,
                "extracted": extracted_result,
                "enriched": enriched_result,
                "summarized": summarized_result,
            }
        }
