"""Parent workflow orchestrating the entire document processing pipeline.

This workflow coordinates the execution of child workflows for:
0. Page Analysis (determines which pages to process + builds document profile)
1. OCR Extraction (only on filtered pages, with page_type metadata)
2. Hybrid Chunking (uses page_section_map from manifest)
3. Tiered Extraction (uses document_profile from manifest, skips Tier 1 LLM)

The manifest from Phase 0 now contains a document_profile that replaces
Tier 1 LLM classification, providing:
- Document type derived from page type distribution
- Section boundaries from consecutive page type runs
- Page-to-section mapping for downstream processing

All child workflows execute on the same task queue: documents-queue
"""

from temporalio import workflow
from datetime import timedelta
from typing import Optional, Dict

from .page_analysis_workflow import PageAnalysisWorkflow
from .ocr_extraction import OCRExtractionWorkflow
from .hybrid_chunking import HybridChunkingWorkflow
from .tiered_extraction import TieredExtractionWorkflow
from .table_extraction import TableExtractionWorkflow
from .entity_resolution import EntityResolutionWorkflow


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
            Dictionary with processing results and statistics
        """
        workflow.logger.info(f"Starting document processing: {document_id}")
        self._status = "processing"
        
        # Analyzes all pages, creates manifest, and builds document profile
        self._current_phase = "page_analysis"
        self._progress = 0.05
        page_manifest = await workflow.execute_child_workflow(
            PageAnalysisWorkflow.run,
            document_id,
            id=f"page-analysis-{document_id}",
            task_queue="documents-queue",
        )
        
        # Extract document profile and page_section_map from manifest
        document_profile = page_manifest.get('document_profile')
        page_section_map = page_manifest.get('page_section_map', {})
        
        # Normalize empty dict to None for cleaner checks downstream
        if page_section_map == {}:
            page_section_map = None
        
        self._document_profile = document_profile
        
        # Validate that document_profile exists (required for new design)
        if not document_profile:
            workflow.logger.warning(
                f"WARNING: No document_profile in manifest for {document_id}. "
                f"Tier 1 LLM will be used as fallback. This should not happen "
                f"with the new optimized pipeline design."
            )
        else:
            workflow.logger.info(
                f"Document profile extracted from manifest: "
                f"type={document_profile.get('document_type')}, "
                f"sections={len(document_profile.get('section_boundaries', []))}, "
                f"confidence={document_profile.get('confidence', 0.0):.2f}"
            )
        
        workflow.logger.info(
            f"Page analysis complete: {page_manifest['total_pages']} pages, "
            f"{len(page_manifest['pages_to_process'])} to process "
            f"({page_manifest['processing_ratio']:.1%})",
            extra={
                "document_type": document_profile.get("document_type") if document_profile else None,
                "section_count": len(document_profile.get("section_boundaries", [])) if document_profile else 0,
                "has_page_section_map": page_section_map is not None,
                "tier1_will_skip": document_profile is not None,
            }
        )
        
        # Only OCRs pages marked as should_process in the manifest
        # Passes page_section_map to store page_type metadata with each page
        self._current_phase = "ocr_extraction"
        self._progress = 0.15
        ocr_result = await workflow.execute_child_workflow(
            OCRExtractionWorkflow.run,
            args=[document_id, page_manifest['pages_to_process'], page_section_map],
            id=f"ocr-{document_id}",
            task_queue="documents-queue",
        )
        workflow.logger.info(
            f"OCR complete: {ocr_result.get('page_count', 0)} pages extracted "
            f"(processed {len(page_manifest['pages_to_process'])} of {page_manifest['total_pages']} pages)",
            extra={
                "has_section_metadata": ocr_result.get('has_section_metadata', False),
            }
        )
        
        # Extract tables structurally from OCR pages (SOV, Loss Run, etc.)
        # Runs in parallel or after OCR, before chunking
        self._current_phase = "table_extraction"
        self._progress = 0.2
        table_result = await workflow.execute_child_workflow(
            TableExtractionWorkflow.run,
            args=[document_id, page_manifest['pages_to_process']],
            id=f"table-extraction-{document_id}",
            task_queue="documents-queue",
        )
        workflow.logger.info(
            f"Table extraction complete: {table_result.get('tables_processed', 0)} tables processed, "
            f"{table_result.get('sov_items', 0)} SOV items, {table_result.get('loss_run_claims', 0)} Loss Run claims",
            extra={
                "tables_found": table_result.get('tables_found', 0),
                "validation_passed": table_result.get('validation_passed', True),
            }
        )
        
        # Section-aware chunking with Docling
        # Uses page_section_map from manifest for consistent section assignment
        self._current_phase = "hybrid_chunking"
        self._progress = 0.3
        chunking_result = await workflow.execute_child_workflow(
            HybridChunkingWorkflow.run,
            args=[document_id, page_section_map],
            id=f"chunking-{document_id}",
            task_queue="documents-queue",
        )
        workflow.logger.info(
            f"Hybrid chunking complete: {chunking_result['chunk_count']} chunks, "
            f"{chunking_result['super_chunk_count']} super-chunks, "
            f"{len(chunking_result['sections_detected'])} sections detected",
            extra={
                "section_source": chunking_result.get('section_source', 'unknown'),
            }
        )
        
        # Extraction workflow for seciton fields and entities extraction with cross-section validation
        self._current_phase = "tiered_extraction"
        self._progress = 0.6
        extraction_result = await workflow.execute_child_workflow(
            TieredExtractionWorkflow.run,
            args=[document_id, document_profile],
            id=f"extraction-{document_id}",
            task_queue="documents-queue",
        )
        workflow.logger.info(
            f"Tiered extraction complete: {extraction_result['total_entities']} entities, "
            f"{extraction_result['total_llm_calls']} LLM calls, "
            f"data quality: {extraction_result['data_quality_score']:.2f}",
            extra={
                "tier1_skipped": extraction_result.get('tier1_skipped', False),
            }
        )
        
        # Entity resolution workflow for canonical resolution and relationship extraction
        self._current_phase = "entity_resolution"
        self._progress = 0.8
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
        
        # Complete
        self._status = "completed"
        self._progress = 1.0
        
        return {
            "status": "completed",
            "document_id": document_id,
            # Phase 0: Page Analysis
            "total_pages": page_manifest['total_pages'],
            "pages_processed": len(page_manifest['pages_to_process']),
            "pages_skipped": len(page_manifest['pages_skipped']),
            "processing_ratio": page_manifest['processing_ratio'],
            # Document Profile (replaces Tier 1 LLM)
            "document_type": (
                document_profile.get("document_type") if document_profile else 
                extraction_result.get('document_type', 'unknown')
            ),
            "document_subtype": document_profile.get("document_subtype") if document_profile else None,
            "profile_confidence": document_profile.get("confidence") if document_profile else None,
            "section_boundaries_count": (
                len(document_profile.get("section_boundaries", [])) if document_profile else 0
            ),
            # Phase 1: OCR
            "page_count": ocr_result.get('page_count', 0),
            "has_section_metadata": ocr_result.get('has_section_metadata', False),
            # Phase 2: Hybrid Chunking
            "chunks": chunking_result['chunk_count'],
            "super_chunks": chunking_result['super_chunk_count'],
            "sections_detected": chunking_result['sections_detected'],
            "total_tokens": chunking_result['total_tokens'],
            "section_source": chunking_result.get('section_source', 'unknown'),
            # Phase 3: Tiered Extraction
            "entities": extraction_result['total_entities'],
            "llm_calls": extraction_result['total_llm_calls'],
            "data_quality_score": extraction_result['data_quality_score'],
            "is_valid": extraction_result['is_valid'],
            "tier1_skipped": extraction_result.get('tier1_skipped', False),
            # Phase 1.5: Table Extraction
            "tables_found": table_result.get('tables_found', 0),
            "tables_processed": table_result.get('tables_processed', 0),
            "sov_items": table_result.get('sov_items', 0),
            "loss_run_claims": table_result.get('loss_run_claims', 0),
            "table_validation_passed": table_result.get('validation_passed', True),
            # Phase 4: Entity Resolution
            "relationships": entity_result['relationship_count'],
        }
