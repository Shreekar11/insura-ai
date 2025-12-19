"""OCR Extraction child workflow.

This workflow orchestrates OCR extraction using activity string names
to avoid importing non-deterministic modules.

UPDATED: Now supports selective page processing based on page manifest.
"""

from temporalio import workflow
from temporalio.common import RetryPolicy
from datetime import timedelta
from typing import Optional, List


@workflow.defn
class OCRExtractionWorkflow:
    """Child workflow for OCR extraction phase."""
    
    @workflow.run
    async def run(
        self, 
        document_id: str,
        pages_to_process: Optional[List[int]] = None
    ) -> dict:
        """
        Extract OCR data from document and store results.
        
        Args:
            document_id: UUID of the document to process
            pages_to_process: Optional list of page numbers to OCR.
                If None, processes all pages (legacy behavior).
                If provided, only OCRs the specified pages (v2 architecture).
        
        Returns:
            Dictionary with page_count and total_text_length
        """
        if pages_to_process:
            workflow.logger.info(
                f"Starting selective OCR for {len(pages_to_process)} pages "
                f"(out of total document pages)"
            )
        else:
            workflow.logger.info("Starting full OCR extraction (all pages)")
        
        # Extract OCR using existing OCRService
        ocr_data = await workflow.execute_activity(
            "extract_ocr",
            args=[document_id, pages_to_process],
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=RetryPolicy(
                maximum_attempts=5,
                initial_interval=timedelta(seconds=5),
                maximum_interval=timedelta(seconds=60),
                backoff_coefficient=2.0,
            ),
        )
        
        return {
            "document_id": ocr_data.get('document_id'),
            "page_count": ocr_data.get('page_count', 0),
        }
