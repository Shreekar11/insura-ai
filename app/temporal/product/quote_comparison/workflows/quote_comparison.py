"""Quote Comparison Temporal workflow - Parent orchestrator."""

from temporalio import workflow
from datetime import timedelta
from typing import Dict, Optional, List

# Import shared stage workflows
from app.temporal.shared.workflows.stages.processed import ProcessedStageWorkflow
from app.temporal.shared.workflows.stages.extracted import ExtractedStageWorkflow
from app.temporal.shared.workflows.stages.enriched import EnrichedStageWorkflow
from app.temporal.shared.workflows.stages.summarized import SummarizedStageWorkflow

# Import product-specific child workflow
from app.temporal.product.quote_comparison.workflows.quote_comparison_core import QuoteComparisonCoreWorkflow

from app.temporal.core.workflow_registry import WorkflowRegistry, WorkflowType
from app.utils.logging import get_logger
from app.temporal.product.quote_comparison.configs.quote_comparison import (
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
class QuoteComparisonWorkflow:
    """Temporal workflow for Quote Comparison.
    
    Orchestrates the complete quote comparison pipeline:
    1. Phase A preflight validation
    2. Document readiness check
    3. Per-document processing stages (shared workflows)
    4. Core comparison (child workflow)
    5. Result persistence
    """

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
        """Execute the quote comparison workflow."""
        workflow_id = payload.get("workflow_id")
        workflow_definition_id = payload.get("workflow_definition_id")
        workflow_name = payload.get("workflow_name")
        documents = payload.get("documents")
        document_ids = [doc.get("document_id") for doc in documents]

        self._status = "running"
        self._progress = 0.0

        # Phase A: Input/Intent Pre-Flight Validation
        self._current_step = "phase_a_preflight"
        self._progress = 0.05
        phase_a_result = await workflow.execute_activity(
            "quote_phase_a_preflight_activity",
            args=[workflow_id, document_ids],
            start_to_close_timeout=timedelta(seconds=30),
        )

        # Check document readiness
        self._current_step = "check_document_readiness"
        self._progress = 0.10
        readiness_result = await workflow.execute_activity(
            "quote_check_document_readiness_activity",
            args=[workflow_id, document_ids],
            start_to_close_timeout=timedelta(seconds=30),
        )

        document_readiness = readiness_result.get("document_readiness", [])

        # Process each document through shared stage workflows
        for doc_readiness in document_readiness:
            doc_id = doc_readiness["document_id"]
            
            # Stage 1: Processed (OCR, page analysis, chunking)
            if not doc_readiness["processed"]:
                self._current_step = f"processing_document_{doc_id}"
                self._progress = 0.15
                processed_result = await workflow.execute_child_workflow(
                    ProcessedStageWorkflow.run,
                    args=[
                        workflow_id, 
                        doc_id, 
                        REQUIRED_SECTIONS,
                        workflow_name
                    ],
                    id=f"quote-comparison-processed-{doc_id}",
                )
                document_profile = processed_result.get("document_profile")
            else:
                document_profile = await workflow.execute_activity(
                    "get_document_profile_activity",
                    args=[doc_id, workflow_name],
                    start_to_close_timeout=timedelta(seconds=30),
                )

            # Stage 2: Extracted (entity extraction)
            if not doc_readiness["extracted"]:
                self._current_step = f"extracting_document_{doc_id}"
                self._progress = 0.25
                await workflow.execute_child_workflow(
                    ExtractedStageWorkflow.run,
                    args=[workflow_id, doc_id, document_profile, REQUIRED_SECTIONS, REQUIRED_ENTITIES],
                    id=f"quote-comparison-extracted-{doc_id}",
                )

            # Stage 3: Enriched (entity resolution)
            if not doc_readiness["enriched"]:
                self._current_step = f"enriching_document_{doc_id}"
                self._progress = 0.35
                await workflow.execute_child_workflow(
                    EnrichedStageWorkflow.run,
                    args=[workflow_id, doc_id],
                    id=f"quote-comparison-enriched-{doc_id}",
                )

            # Stage 4: Summarized (indexing)
            if not doc_readiness["indexed"]:
                self._current_step = f"indexing_document_{doc_id}"
                self._progress = 0.45
                await workflow.execute_child_workflow(
                    SummarizedStageWorkflow.run,
                    args=[workflow_id, doc_id, REQUIRED_SECTIONS],
                    id=f"quote-comparison-indexed-{doc_id}",
                )

        # Core Quote Comparison
        self._current_step = "core_comparison"
        self._progress = 0.60
        core_result = await workflow.execute_child_workflow(
            QuoteComparisonCoreWorkflow.run,
            args=[workflow_id, document_ids],
            id=f"quote-comparison-core-{workflow_id}",
        )

        phase_b_result = core_result.get("phase_b_result")
        comparison_result = core_result.get("comparison_result")

        # Persist Result
        self._current_step = "persist_result"
        self._progress = 0.95
        persist_result = await workflow.execute_activity(
            "persist_quote_comparison_result_activity",
            args=[
                workflow_id, 
                workflow_definition_id, 
                document_ids, 
                comparison_result,
                None  # broker_summary - to be added later
            ],
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
