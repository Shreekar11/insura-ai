"""Page Analysis workflow for document page classification.

This workflow orchestrates the page analysis phase to determine which pages
should undergo full OCR processing, achieving 70-85% cost reduction.

Now returns full manifest with document_profile and page_section_map
"""

from temporalio import workflow
from temporalio.common import RetryPolicy
from datetime import timedelta
from typing import Dict

from app.utils.workflow_schemas import (
    PageAnalysisOutputSchema,
    validate_workflow_output,
)


@workflow.defn
class PageAnalysisWorkflow:
    """Workflow for analyzing and classifying document pages.
    
    This workflow orchestrates the page analysis phase to determine which pages
    should undergo full OCR processing, achieving 70-85% cost reduction.
    
    Workflow Steps:
    1. Extracts lightweight signals from all pages (using Docling)
    2. Classifies pages using rule-based patterns
    3. Detects duplicate pages within the document
    4. Builds document profile
    5. Creates a page manifest with document_profile and page_section_map
    
    Performance:
        Uses singleton instances for stateless components in activities to
        minimize initialization overhead across multiple document processing.
    
    Output:
        Returns full manifest including document_profile and page_section_map
        for downstream workflows (OCR, chunking, extraction).
    """
    
    @workflow.run
    async def run(self, document_id: str) -> Dict:
        """Execute page analysis and create processing manifest with document profile.
        
        Args:
            document_id: UUID string of the document to analyze
            
        Returns:
            Dictionary with full manifest including:
                - document_id: str
                - total_pages: int
                - pages_to_process: List[int]
                - pages_skipped: List[int]
                - processing_ratio: float
                - document_profile: Dict (replaces Tier 1 LLM)
                    - document_type: str
                    - document_subtype: Optional[str]
                    - confidence: float
                    - section_boundaries: List[Dict]
                    - page_section_map: Dict[int, str]
                - page_section_map: Dict[int, str] (for OCR/chunking)
        """
        workflow.logger.info(f"Starting page analysis for document: {document_id}")
        
        # Activity 1: Extract signals from all pages
        # Uses Docling's selective extraction (bounding boxes) to get top lines,
        # text density, table presence, etc. without full OCR
        page_signals = await workflow.execute_activity(
            "extract_page_signals",
            document_id,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(
                maximum_attempts=3,
                initial_interval=timedelta(seconds=5),
                maximum_interval=timedelta(seconds=30),
                backoff_coefficient=2.0,
            ),
        )
        
        workflow.logger.info(f"Extracted signals from {len(page_signals)} pages")
        
        # Activity 2: Classify pages using rule-based classifier
        # Applies insurance-specific keyword patterns and structural heuristics
        # Also performs duplicate detection using MinHash
        classifications = await workflow.execute_activity(
            "classify_pages",
            args=[document_id, page_signals],
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=RetryPolicy(
                maximum_attempts=3,
                initial_interval=timedelta(seconds=5),
                maximum_interval=timedelta(seconds=30),
                backoff_coefficient=2.0,
            ),
        )
        
        workflow.logger.info(f"Classified {len(classifications)} pages")
        
        # Activity 3: Create and persist page manifest with document profile
        # This activity now builds document_profile and page_section_map
        manifest = await workflow.execute_activity(
            "create_page_manifest",
            args=[document_id, classifications],
            start_to_close_timeout=timedelta(minutes=1),
            retry_policy=RetryPolicy(
                maximum_attempts=3,
                initial_interval=timedelta(seconds=5),
                maximum_interval=timedelta(seconds=30),
                backoff_coefficient=2.0,
            ),
        )
        
        processing_ratio = manifest.get('processing_ratio', 0.0)
        document_profile = manifest.get('document_profile')
        page_section_map = manifest.get('page_section_map', {})
        
        workflow.logger.info(
            f"Page analysis complete: {manifest['total_pages']} pages, "
            f"{len(manifest['pages_to_process'])} to process "
            f"({processing_ratio:.1%} processing ratio)",
            extra={
                "document_type": document_profile.get("document_type") if document_profile else None,
                "section_count": len(document_profile.get("section_boundaries", [])) if document_profile else 0,
                "has_page_section_map": bool(page_section_map),
            }
        )
        
        # Validate output against schema (fail fast if invalid)
        validated_output = validate_workflow_output(
            manifest,
            PageAnalysisOutputSchema,
            "PageAnalysisWorkflow"
        )
        
        workflow.logger.info("Page analysis output validated against schema")
        
        # Return FULL manifest including document_profile and page_section_map
        return validated_output
