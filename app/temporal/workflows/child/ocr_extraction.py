"""OCR Extraction child workflow.

This workflow orchestrates OCR extraction using activity string names
to avoid importing non-deterministic modules.

UPDATED: Now supports selective page processing based on page manifest
and accepts page_section_map to store page_type metadata with each page.
"""

from temporalio import workflow
from temporalio.common import RetryPolicy
from datetime import timedelta
from typing import Optional, List, Dict

from app.utils.workflow_schemas import (
    OCRExtractionOutputSchema,
    validate_workflow_output,
)


@workflow.defn
class OCRExtractionWorkflow:
    """Child workflow for OCR extraction phase."""
    
    @workflow.run
    async def run(
        self, 
        workflow_id: str,
        document_id: str,
        pages_to_process: Optional[List[int]] = None,
        page_section_map: Optional[Dict[int, str]] = None,
    ) -> dict:
        """
        Extract OCR data from document and store results.
        
        Args:
            document_id: UUID of the document to process
            pages_to_process: Optional list of page numbers to OCR.
                If None, processes all pages (legacy behavior).
                If provided, only OCRs the specified pages.
            page_section_map: Optional mapping of page numbers to section types
                from Phase 0 page analysis manifest. If provided, stores
                page_type metadata with each extracted page.
        
        Returns:
            Dictionary with page_count, has_section_metadata, etc.
        """
        # Normalize empty dict to None
        if page_section_map == {}:
            page_section_map = None
        
        has_section_map = page_section_map is not None
        
        if pages_to_process:
            workflow.logger.info(
                f"Starting selective OCR for {len(pages_to_process)} pages "
                f"(section_map: {'provided' if has_section_map else 'none'})",
                extra={"workflow_id": workflow_id}
            )
        else:
            workflow.logger.info(
                f"Starting full OCR extraction (all pages, "
                f"section_map: {'provided' if has_section_map else 'none'})",
                extra={"workflow_id": workflow_id}
            )
        
        # Extract OCR using existing OCRService with page_section_map
        ocr_data = await workflow.execute_activity(
            "extract_ocr",
            args=[workflow_id, document_id, pages_to_process, page_section_map],
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=RetryPolicy(
                maximum_attempts=5,
                initial_interval=timedelta(seconds=5),
                maximum_interval=timedelta(seconds=60),
                backoff_coefficient=2.0,
            ),
        )
        
        output = {
            "document_id": ocr_data.get('document_id'),
            "page_count": ocr_data.get('page_count', 0),
            "pages_processed": ocr_data.get('pages_processed', []),
            "selective": ocr_data.get('selective', False),
            "has_section_metadata": ocr_data.get('has_section_metadata', False),
            "section_distribution": ocr_data.get('section_distribution'),
        }
        
        # Validate output against schema (fail fast if invalid)
        validated_output = validate_workflow_output(
            output,
            OCRExtractionOutputSchema,
            "OCRExtractionWorkflow"
        )
        
        workflow.logger.info("OCR extraction output validated against schema")
        
        return validated_output
