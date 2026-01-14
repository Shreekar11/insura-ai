"""OCR Extraction child workflow."""

from temporalio import workflow
from temporalio.common import RetryPolicy
from datetime import timedelta
from typing import Optional, List, Dict

from app.utils.workflow_schemas import (
    OCRExtractionOutputSchema,
    validate_workflow_output,
)
from app.temporal.core.workflow_registry import WorkflowRegistry, WorkflowType


@WorkflowRegistry.register(category=WorkflowType.SHARED)
@workflow.defn
class OCRExtractionWorkflow:
    """Child workflow for OCR extraction phase."""
    
    @workflow.run
    async def run(
        self, 
        workflow_id: str,
        document_id: str,
    ) -> dict:
        """Extract OCR data from document and store results."""
        workflow.logger.info(
            f"Starting full OCR extraction (all pages)",
            extra={"workflow_id": workflow_id}
        )
        
        ocr_data = await workflow.execute_activity(
            "extract_ocr",
            args=[workflow_id, document_id],
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
            "markdown_pages": ocr_data.get('markdown_pages', []),
            "selective": False,
            "has_section_metadata": False,
            "section_distribution": None,
        }
        
        return validate_workflow_output(
            output,
            OCRExtractionOutputSchema,
            "OCRExtractionWorkflow"
        )
