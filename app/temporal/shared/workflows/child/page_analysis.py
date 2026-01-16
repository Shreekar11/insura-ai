"""Page Analysis workflow for document page classification."""

from temporalio import workflow
from temporalio.common import RetryPolicy
from datetime import timedelta
from typing import Dict, Optional, List, Tuple, Any

from app.schemas.product.shared_workflow_schemas import (
    PageAnalysisOutputSchema,
    validate_workflow_output,
)
from app.temporal.core.workflow_registry import WorkflowRegistry, WorkflowType


@WorkflowRegistry.register(category=WorkflowType.SHARED)
@workflow.defn
class PageAnalysisWorkflow:
    """Workflow for analyzing and classifying document pages."""
    
    @workflow.run
    async def run(
        self, 
        document_id: str, 
        markdown_pages: List[Tuple[str, int, Optional[Dict[str, Any]]]] = None,
        workflow_id: Optional[str] = None,
        workflow_name: Optional[str] = None,
    ) -> Dict:
        """Execute page analysis and create processing manifest with document profile."""
        if markdown_pages:
            page_signals = await workflow.execute_activity(
                "extract_page_signals_from_markdown",
                args=[document_id, markdown_pages],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(
                    maximum_attempts=3,
                    initial_interval=timedelta(seconds=5),
                    maximum_interval=timedelta(seconds=30),
                    backoff_coefficient=2.0,
                ),
            )
        else:
            page_signals = await workflow.execute_activity(
                "extract_page_signals",
                args=[document_id],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(
                    maximum_attempts=3,
                    initial_interval=timedelta(seconds=5),
                    maximum_interval=timedelta(seconds=30),
                    backoff_coefficient=2.0,
                ),
            )
        
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
        
        manifest = await workflow.execute_activity(
            "create_page_manifest",
            args=[document_id, classifications, workflow_name],
            start_to_close_timeout=timedelta(minutes=1),
            retry_policy=RetryPolicy(
                maximum_attempts=3,
                initial_interval=timedelta(seconds=5),
                maximum_interval=timedelta(seconds=30),
                backoff_coefficient=2.0,
            ),
        )
        
        return validate_workflow_output(
            manifest,
            PageAnalysisOutputSchema,
            "PageAnalysisWorkflow"
        )
