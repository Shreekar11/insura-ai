"""Temporal workflow for table extraction."""

from temporalio import workflow
from temporalio.common import RetryPolicy
from typing import Dict, Any, Optional, List
from datetime import timedelta

from app.schemas.product.shared_workflow_schemas import (
    TableExtractionOutputSchema,
    validate_workflow_output,
)
from app.temporal.core.workflow_registry import WorkflowRegistry, WorkflowType


@WorkflowRegistry.register(category=WorkflowType.SHARED)
@workflow.defn
class TableExtractionWorkflow:
    """Workflow for extracting tables from documents."""
    
    @workflow.run
    async def run(
        self,
        workflow_id: str,
        document_id: str,
        page_numbers: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """Execute table extraction workflow."""
        result = await workflow.execute_activity(
            "extract_tables",
            args=[workflow_id, document_id, None, page_numbers],
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),
                backoff_coefficient=2.0,
                maximum_interval=timedelta(minutes=1),
                maximum_attempts=3
            )
        )
        
        return validate_workflow_output(
            result,
            TableExtractionOutputSchema,
            "TableExtractionWorkflow"
        )
