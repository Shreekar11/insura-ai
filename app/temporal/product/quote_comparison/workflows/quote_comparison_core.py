"""Core Quote Comparison logic child workflow."""

from temporalio import workflow
from datetime import timedelta
from typing import List, Dict

from app.temporal.core.workflow_registry import WorkflowRegistry, WorkflowType


@WorkflowRegistry.register(category=WorkflowType.BUSINESS)
@workflow.defn
class QuoteComparisonCoreWorkflow:
    """Child workflow encapsulating core quote comparison steps.
    
    Executes:
    1. Phase B preflight validation
    2. Coverage normalization
    3. Quality evaluation
    4. Side-by-side comparison matrix generation
    """

    @workflow.run
    async def run(self, workflow_id: str, document_ids: List[str]) -> dict:
        """Execute Phase B, Normalization, Quality Evaluation, and Comparison."""
        
        workflow.logger.info(
            f"Starting QuoteComparisonCoreWorkflow for workflow {workflow_id}"
        )

        # 1. Phase B: Capability Pre-Flight Validation
        phase_b_result = await workflow.execute_activity(
            "quote_phase_b_preflight_activity",
            args=[workflow_id, document_ids],
            start_to_close_timeout=timedelta(seconds=60),
        )

        # 2. Coverage Normalization
        normalization_result = await workflow.execute_activity(
            "coverage_normalization_activity",
            args=[workflow_id, document_ids],
            start_to_close_timeout=timedelta(seconds=120),
        )

        # 3. Quality Evaluation
        quality_result = await workflow.execute_activity(
            "quality_evaluation_activity",
            args=[workflow_id, normalization_result.get("normalized_coverages", {})],
            start_to_close_timeout=timedelta(seconds=60),
        )

        # 4. Generate Side-by-Side Comparison Matrix
        comparison_result = await workflow.execute_activity(
            "generate_comparison_matrix_activity",
            args=[workflow_id, document_ids],
            start_to_close_timeout=timedelta(seconds=180),
        )

        return {
            "phase_b_result": phase_b_result,
            "normalization_result": normalization_result,
            "quality_result": quality_result,
            "comparison_result": comparison_result.get("comparison_result"),
        }
