"""OCR Extraction child workflow.

This workflow orchestrates OCR extraction using activity string names
to avoid importing non-deterministic modules.
"""

from temporalio import workflow
from datetime import timedelta


@workflow.defn
class OCRExtractionWorkflow:
    """Child workflow for OCR extraction phase."""
    
    @workflow.run
    async def run(self, document_id: str) -> dict:
        """
        Extract OCR data from document and store results.
        
        Args:
            document_id: UUID of the document to process
            
        Returns:
            Dictionary with page_count and total_text_length
        """
        # Extract OCR using existing OCRService
        ocr_data = await workflow.execute_activity(
            "extract_ocr",
            document_id,
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=workflow.RetryPolicy(
                maximum_attempts=5,
                initial_interval=timedelta(seconds=5),
                maximum_interval=timedelta(seconds=60),
                backoff_coefficient=2.0,
            ),
        )
        
        # Store results in database
        await workflow.execute_activity(
            "store_ocr_results",
            [document_id, ocr_data],
            start_to_close_timeout=timedelta(minutes=2),
        )
        
        return {
            "page_count": len(ocr_data['pages']),
            "total_text_length": sum(len(p.get('text', '')) for p in ocr_data['pages']),
        }
