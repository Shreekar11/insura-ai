"""Policy Comparison Temporal workflow."""

from temporalio import workflow
from datetime import timedelta
from typing import Dict, Optional, List

# Import shared stage workflows
from app.temporal.shared.workflows.stages.processed import ProcessedStageWorkflow
from app.temporal.shared.workflows.stages.extracted import ExtractedStageWorkflow
from app.temporal.shared.workflows.stages.enriched import EnrichedStageWorkflow
from app.temporal.shared.workflows.stages.summarized import SummarizedStageWorkflow

# Import product-specific child workflow
from app.temporal.product.policy_comparison.workflows.policy_comparison_core import PolicyComparisonCoreWorkflow

from app.temporal.core.workflow_registry import WorkflowRegistry, WorkflowType
from app.utils.logging import get_logger
from app.temporal.product.policy_comparison.configs.policy_comparison import (
    PROCESSING_CONFIG,
    REQUIRED_SECTIONS,
    REQUIRED_ENTITIES,
)

LOGGER = get_logger(__name__)


@WorkflowRegistry.register(
    category=WorkflowType.BUSINESS,
    task_queue="documents-queue",
)
@workflow.defn
class PolicyComparisonWorkflow:
    """Temporal workflow for Policy Comparison."""

    def __init__(self):
        self._status = "initialized"
        self._current_step: str | None = None
        self._progress = 0.0

    @workflow.query
    def get_status(self) -> dict:
        """Query handler for real-time status updates."""
        return {
            "status": self._status,
            "current_step": self._current_step,
            "progress": self._progress,
        }

    @workflow.run
    async def run(self, payload: Dict) -> dict:
        """Execute the policy comparison workflow."""
        workflow_id = payload.get("workflow_id")
        workflow_definition_id = payload.get("workflow_definition_id")
        documents = payload.get("documents")
        document_ids = [doc.get("document_id") for doc in documents]

        self._status = "running"
        self._progress = 0.0

        # Phase A: Input/Intent Pre-Flight Validation
        self._current_step = "phase_a_preflight"
        self._progress = 0.05
        phase_a_result = await workflow.execute_activity(
            "phase_a_preflight_activity",
            args=[workflow_id, document_ids],
            start_to_close_timeout=timedelta(seconds=30),
        )

        # Check document readiness
        self._current_step = "check_document_readiness"
        self._progress = 0.10
        readiness_result = await workflow.execute_activity(
            "check_document_readiness_activity",
            args=[workflow_id, document_ids],
            start_to_close_timeout=timedelta(seconds=30),
        )

        document_readiness = readiness_result.get("document_readiness", [])

        for doc_readiness in document_readiness:
            doc_id = doc_readiness["document_id"]
            
            # Stage 1: Processed
            if not doc_readiness["processed"]:
                self._current_step = f"processing_document_{doc_id}"
                self._progress = 0.15
                processed_result = await workflow.execute_child_workflow(
                    ProcessedStageWorkflow.run,
                    args=[
                        workflow_id, 
                        doc_id, 
                        REQUIRED_SECTIONS
                    ],
                    id=f"policy-comparison-processed-{doc_id}",
                )
                document_profile = processed_result.get("document_profile")
            else:
                document_profile = await workflow.execute_activity(
                    "get_document_profile_activity",
                    args=[doc_id],
                    start_to_close_timeout=timedelta(seconds=30),
                )

            # Stage 2: Extracted
            if not doc_readiness["extracted"]:
                self._current_step = f"extracting_document_{doc_id}"
                self._progress = 0.20
                await workflow.execute_child_workflow(
                    ExtractedStageWorkflow.run,
                    args=[workflow_id, doc_id, document_profile, REQUIRED_SECTIONS, REQUIRED_ENTITIES],
                    id=f"policy-comparison-extracted-{doc_id}",
                )

            # Stage 3: Enriched
            if not doc_readiness["enriched"]:
                self._current_step = f"enriching_document_{doc_id}"
                self._progress = 0.25
                await workflow.execute_child_workflow(
                    EnrichedStageWorkflow.run,
                    args=[workflow_id, doc_id],
                    id=f"policy-comparison-enriched-{doc_id}",
                )

            # Stage 4: Summarized
            if not doc_readiness["indexed"]:
                self._current_step = f"indexing_document_{doc_id}"
                self._progress = 0.30
                await workflow.execute_child_workflow(
                    SummarizedStageWorkflow.run,
                    args=[workflow_id, doc_id, REQUIRED_SECTIONS],
                    id=f"policy-comparison-indexed-{doc_id}",
                )

        # Core Comparison
        self._current_step = "core_comparison"
        self._progress = 0.60
        core_result = await workflow.execute_child_workflow(
            PolicyComparisonCoreWorkflow.run,
            args=[workflow_id, document_ids],
            id=f"policy-comparison-core-{workflow_id}",
        )

        phase_b_result = core_result.get("phase_b_result")
        alignment_result = core_result.get("alignment_result")
        reasoning_result = core_result.get("reasoning_result")

        # Persist Result
        self._current_step = "persist_result"
        self._progress = 0.95
        persist_result = await workflow.execute_activity(
            "persist_comparison_result_activity",
            args=[workflow_id, workflow_definition_id, document_ids, alignment_result, reasoning_result, phase_b_result],
            start_to_close_timeout=timedelta(seconds=60),
        )

        self._status = "completed"
        self._progress = 1.0
        self._current_step = "completed"

        return {
            "status": persist_result.get("status"),
            "workflow_id": str(workflow_id),
            "comparison_summary": persist_result.get("comparison_summary"),
            "total_changes": persist_result.get("total_changes"),
            "comparison_scope": phase_b_result.get("comparison_scope", "full"),
        }
