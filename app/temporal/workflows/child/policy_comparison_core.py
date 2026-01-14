"""Core Policy Comparison logic child workflow."""

from temporalio import workflow
from datetime import timedelta
from typing import List, Dict

@workflow.defn
class PolicyComparisonCoreWorkflow:
    """Child workflow encapsulating core comparison steps."""

    @workflow.run
    async def run(self, workflow_id: str, document_ids: List[str]) -> dict:
        """Execute Phase B, Alignment, Comparison, and Reasoning."""
        
        workflow.logger.info(
            f"Starting PolicyComparisonCoreWorkflow for workflow {workflow_id}",
            extra={"workflow_id": workflow_id, "document_ids": document_ids}
        )

        # 1. Phase B: Capability Pre-Flight Validation
        phase_b_result = await workflow.execute_activity(
            "phase_b_preflight_activity",
            args=[workflow_id, document_ids],
            start_to_close_timeout=timedelta(seconds=60),
        )
        workflow.logger.info(f"Phase B completed in child workflow: {phase_b_result.get('comparison_scope')}")

        # 2. Section Alignment
        alignment_result = await workflow.execute_activity(
            "section_alignment_activity",
            args=[workflow_id, document_ids],
            start_to_close_timeout=timedelta(seconds=120),
        )
        workflow.logger.info(f"Alignment completed in child workflow: {alignment_result.get('alignment_count')} alignments")

        # 3. Detailed Entity Comparison
        diff_result = await workflow.execute_activity(
            "detailed_comparison_activity",
            args=[workflow_id, alignment_result],
            start_to_close_timeout=timedelta(seconds=120),
        )
        workflow.logger.info(f"Detailed comparison completed in child workflow: {diff_result.get('change_count')} changes")

        # 4. Generate Comparison Reasoning
        reasoning_result = await workflow.execute_activity(
            "generate_comparison_reasoning_activity",
            args=[workflow_id, diff_result],
            start_to_close_timeout=timedelta(seconds=120),
        )
        workflow.logger.info(f"Reasoning completed in child workflow")

        return {
            "phase_b_result": phase_b_result,
            "alignment_result": alignment_result,
            "reasoning_result": reasoning_result,
        }
