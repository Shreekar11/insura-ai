"""Temporal workflow for table extraction.

This workflow orchestrates table extraction as part of Phase 5.
Tables are extracted structurally from documents and persisted
as first-class entities (SOVItem, LossRunClaim).

Uses activity string names to avoid importing non-deterministic modules.
"""

from temporalio import workflow
from temporalio.common import RetryPolicy
from typing import Dict, Any, Optional, List
from datetime import timedelta

from app.utils.workflow_schemas import (
    TableExtractionOutputSchema,
    validate_workflow_output,
)


@workflow.defn
class TableExtractionWorkflow:
    """Workflow for extracting tables from documents.
    
    This workflow implements Phase 5 table extraction:
    - Extracts structured tables (not text)
    - Classifies table types (SOV, Loss Run, etc.)
    - Normalizes rows into domain objects
    - Validates extracted data
    - Persists to database
    """
    
    @workflow.run
    async def run(
        self,
        document_id: str,
        workflow_id: Optional[str] = None,
        page_numbers: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """Execute table extraction workflow.
        
        Args:
            document_id: Document UUID as string
            page_numbers: Optional list of page numbers to process
            
        Returns:
            Dictionary with extraction results and statistics
        """
        workflow.logger.info(
            f"Starting table extraction workflow for document: {document_id}",
            extra={
                "document_id": document_id,
                "page_numbers": page_numbers,
                "workflow_id": workflow_id
            }
        )
        
        # Execute table extraction activity using string name
        # This avoids importing non-deterministic modules in workflows
        result = await workflow.execute_activity(
            "extract_tables",
            args=[document_id, None, page_numbers],
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),
                backoff_coefficient=2.0,
                maximum_interval=timedelta(minutes=1),
                maximum_attempts=3
            )
        )
        
        workflow.logger.info(
            f"Table extraction workflow complete for document: {document_id}",
            extra={
                "document_id": document_id,
                "tables_processed": result.get("tables_processed", 0),
                "sov_items": result.get("sov_items", 0),
                "loss_run_claims": result.get("loss_run_claims", 0),
                "validation_passed": result.get("validation_passed", True)
            }
        )
        
        # Validate output against schema (fail fast if invalid)
        validated_output = validate_workflow_output(
            result,
            TableExtractionOutputSchema,
            "TableExtractionWorkflow"
        )
        
        workflow.logger.info("Table extraction output validated against schema")
        
        return validated_output

