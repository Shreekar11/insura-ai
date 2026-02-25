"""Policy Comparison Temporal workflow."""

from temporalio import workflow
from datetime import timedelta
from typing import Dict, Optional, List, Any

from app.temporal.shared.workflows.mixin import DocumentProcessingMixin, DocumentProcessingConfig
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
class PolicyComparisonWorkflow(DocumentProcessingMixin):
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
        workflow_name = payload.get("workflow_name")
        documents = payload.get("documents")
        document_ids = [doc.get("document_id") for doc in documents]
        doc_names = [doc.get("document_name") for doc in documents]

        self._status = "running"
        self._progress = 0.0

        # Phase A: Input/Intent Pre-Flight Validation
        self._current_step = "phase_a_preflight"
        self._progress = 0.05
        await workflow.execute_activity(
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

        # Process documents via mixin
        for i, doc_readiness in enumerate(document_readiness):
            doc_id = doc_readiness["document_id"]
            
            # Check if any processing is needed
            if not all([doc_readiness["processed"], doc_readiness["extracted"], 
                       doc_readiness["enriched"], doc_readiness["indexed"]]):
                
                self._current_step = f"processing_document_{doc_id}"
                self._progress = 0.15 + (i * 0.1)
                
                config = DocumentProcessingConfig(
                    workflow_id=workflow_id,
                    workflow_name=workflow_name,
                    target_sections=REQUIRED_SECTIONS,
                    target_entities=REQUIRED_ENTITIES,
                    skip_processed=doc_readiness["processed"],
                    skip_extraction=doc_readiness["extracted"],
                    skip_enrichment=doc_readiness["enriched"],
                    skip_indexing=doc_readiness["indexed"],
                    document_name=doc_readiness.get("document_name") or next((d.get("document_name") for d in documents if d.get("document_id") == doc_id), None)
                )
                
                await self.process_document(doc_id, config)

        # Core Comparison
        self._current_step = "core_comparison"
        self._progress = 0.60

        await workflow.execute_activity(
            "emit_workflow_event",
            args=[workflow_id, "workflow:progress", {"message": "Starting policy comparison...", "stage_name": "comparison"}],
            start_to_close_timeout=timedelta(seconds=10),
        )

        core_result = await self._execute_core_comparison(workflow_id, document_ids, doc_names)

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

        # Entity Comparison
        self._current_step = "entity_comparison"
        self._progress = 0.98
        await workflow.execute_activity(
            "policy_entity_comparison_activity",
            args=[workflow_id, document_ids, doc_names],
            start_to_close_timeout=timedelta(seconds=120),
        )

        await workflow.execute_activity(
            "emit_workflow_event",
            args=[workflow_id, "workflow:progress", {"message": "Policy comparison completed successfully."}],
            start_to_close_timeout=timedelta(seconds=10),
        )

        self._status = "completed"
        self._progress = 1.0
        self._current_step = "completed"

        # Persist status to database
        await workflow.execute_activity(
            "update_workflow_status",
            args=[workflow_id, "completed"],
            start_to_close_timeout=timedelta(minutes=1),
        )

        return {
            "status": persist_result.get("status"),
            "workflow_id": str(workflow_id),
            "comparison_summary": persist_result.get("comparison_summary"),
            "total_changes": persist_result.get("total_changes"),
            "comparison_scope": phase_b_result.get("comparison_scope", "full"),
        }

    async def _execute_core_comparison(self, workflow_id: str, document_ids: List[str], document_names: List[str]) -> Dict[str, Any]:
        """Execute core comparison logic (Phase B, Alignment, Comparison, and Reasoning)."""
        workflow.logger.info(f"Starting core comparison logic for workflow {workflow_id}")

        doc_msg = " and ".join(document_names) if len(document_names) > 1 else document_names[0]

        # 1. Phase B: Capability Pre-Flight Validation
        phase_b_result = await workflow.execute_activity(
            "phase_b_preflight_activity",
            args=[workflow_id, document_ids],
            start_to_close_timeout=timedelta(seconds=60),
        )

        # 2. Section Alignment
        await workflow.execute_activity(
            "emit_workflow_event",
            args=[workflow_id, "workflow:progress", {"message": f"Aligning sections from {doc_msg}"}],
            start_to_close_timeout=timedelta(seconds=10),
        )
        alignment_result = await workflow.execute_activity(
            "section_alignment_activity",
            args=[workflow_id, document_ids],
            start_to_close_timeout=timedelta(seconds=120),
        )

        # 3. Detailed Entity Comparison
        await workflow.execute_activity(
            "emit_workflow_event",
            args=[workflow_id, "workflow:progress", {"message": f"Comparing sections from {doc_msg}"}],
            start_to_close_timeout=timedelta(seconds=10),
        )
        diff_result = await workflow.execute_activity(
            "detailed_comparison_activity",
            args=[workflow_id, alignment_result],
            start_to_close_timeout=timedelta(seconds=120),
        )

        # 4. Generate Comparison Reasoning
        await workflow.execute_activity(
            "emit_workflow_event",
            args=[workflow_id, "workflow:progress", {"message": f"Generating insights for {doc_msg}"}],
            start_to_close_timeout=timedelta(seconds=10),
        )
        reasoning_result = await workflow.execute_activity(
            "generate_comparison_reasoning_activity",
            args=[workflow_id, diff_result],
            start_to_close_timeout=timedelta(seconds=120),
        )

        return {
            "phase_b_result": phase_b_result,
            "alignment_result": alignment_result,
            "reasoning_result": reasoning_result,
        }
