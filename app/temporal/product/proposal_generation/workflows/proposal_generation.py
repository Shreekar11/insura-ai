"""Proposal Generation Temporal Workflow.

Orchestrates the complete proposal generation pipeline:
1. Pre-flight validation (require exactly 2 documents)
2. Document processing through shared stage workflows
3. Proposal-specific comparison and narrative generation via child workflow
"""

from temporalio import workflow
from datetime import timedelta
from typing import Dict, List, Any

# Import shared stage workflows
from app.temporal.shared.workflows.stages.processed import ProcessedStageWorkflow
from app.temporal.shared.workflows.stages.extracted import ExtractedStageWorkflow
from app.temporal.shared.workflows.stages.enriched import EnrichedStageWorkflow
from app.temporal.shared.workflows.stages.summarized import SummarizedStageWorkflow

# Import proposal-specific child workflow
from app.temporal.product.proposal_generation.workflows.proposal_generation_core import ProposalGenerationCoreWorkflow

from app.temporal.core.workflow_registry import WorkflowRegistry, WorkflowType
from app.utils.logging import get_logger
from app.temporal.product.proposal_generation.configs.proposal_generation import (
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
class ProposalGenerationWorkflow:
    """Temporal workflow for Proposal Generation.
    
    This is the main entry point for generating insurance proposals.
    It requires exactly 2 documents: an expiring policy and a renewal quote.
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
        """Execute the proposal generation workflow.
        
        Args:
            payload: {
                "workflow_id": str,
                "workflow_definition_id": str,
                "documents": [{"document_id": str, "url": str}, ...],
                "metadata": Dict (optional)
            }
        """
        workflow_id = payload.get("workflow_id")
        workflow_definition_id = payload.get("workflow_definition_id")
        documents = payload.get("documents", [])
        document_ids = [doc.get("document_id") for doc in documents]

        self._status = "running"
        self._progress = 0.0

        # Phase A: Pre-flight validation (require exactly 2 documents)
        self._current_step = "preflight_validation"
        self._progress = 0.05
        
        if len(document_ids) != 2:
            self._status = "failed"
            return {
                "status": "FAILED",
                "error": f"Proposal generation requires exactly 2 documents, got {len(document_ids)}",
            }

        # Check document readiness
        self._current_step = "check_document_readiness"
        self._progress = 0.10
        readiness_result = await workflow.execute_activity(
            "check_document_readiness_activity",
            args=[workflow_id, document_ids],
            start_to_close_timeout=timedelta(seconds=30),
        )

        document_readiness = readiness_result.get("document_readiness", [])

        # Process each document through shared stage workflows
        for idx, doc_readiness in enumerate(document_readiness):
            doc_id = doc_readiness["document_id"]
            base_progress = 0.10 + (idx * 0.30)  # 10% for each doc processing block
            
            # Stage 1: Processed
            if not doc_readiness.get("processed"):
                self._current_step = f"processing_document_{doc_id}"
                self._progress = base_progress + 0.05
                processed_result = await workflow.execute_child_workflow(
                    ProcessedStageWorkflow.run,
                    args=[
                        workflow_id, 
                        doc_id, 
                        REQUIRED_SECTIONS
                    ],
                    id=f"proposal-processed-{doc_id}",
                )
                document_profile = processed_result.get("document_profile")
            else:
                document_profile = await workflow.execute_activity(
                    "get_document_profile_activity",
                    args=[doc_id],
                    start_to_close_timeout=timedelta(seconds=30),
                )

            # Stage 2: Extracted
            if not doc_readiness.get("extracted"):
                self._current_step = f"extracting_document_{doc_id}"
                self._progress = base_progress + 0.10
                await workflow.execute_child_workflow(
                    ExtractedStageWorkflow.run,
                    args=[workflow_id, doc_id, document_profile, REQUIRED_SECTIONS, REQUIRED_ENTITIES],
                    id=f"proposal-extracted-{doc_id}",
                )

            # Stage 3: Enriched
            if not doc_readiness.get("enriched"):
                self._current_step = f"enriching_document_{doc_id}"
                self._progress = base_progress + 0.15
                await workflow.execute_child_workflow(
                    EnrichedStageWorkflow.run,
                    args=[workflow_id, doc_id],
                    id=f"proposal-enriched-{doc_id}",
                )

            # Stage 4: Summarized
            if not doc_readiness.get("indexed"):
                self._current_step = f"indexing_document_{doc_id}"
                self._progress = base_progress + 0.20
                await workflow.execute_child_workflow(
                    SummarizedStageWorkflow.run,
                    args=[workflow_id, doc_id, REQUIRED_SECTIONS],
                    id=f"proposal-indexed-{doc_id}",
                )

        # Phase B: Core Proposal Generation (child workflow)
        self._current_step = "proposal_generation_core"
        self._progress = 0.70
        core_result = await workflow.execute_child_workflow(
            ProposalGenerationCoreWorkflow.run,
            args=[workflow_id, document_ids, workflow_definition_id],
            id=f"proposal-core-{workflow_id}",
        )

        self._status = "completed"
        self._progress = 1.0
        self._current_step = "completed"

        return {
            "status": core_result.get("status", "COMPLETED"),
            "workflow_id": str(workflow_id),
            "proposal_id": core_result.get("proposal_id"),
            "pdf_path": core_result.get("pdf_path"),
            "expiring_document_id": core_result.get("expiring_document_id"),
            "renewal_document_id": core_result.get("renewal_document_id"),
            "total_changes": core_result.get("total_changes", 0),
        }
