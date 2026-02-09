"""Quote Comparison Temporal workflow - Parent orchestrator."""

from temporalio import workflow
from datetime import timedelta
from typing import Dict, Optional, List

from app.temporal.shared.workflows.mixin import DocumentProcessingMixin, DocumentProcessingConfig
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
class QuoteComparisonWorkflow(DocumentProcessingMixin):
    """Temporal workflow for Quote Comparison."""

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
        metadata = payload.get("metadata", {}) # Assuming metadata might contain document names

        self._status = "running"
        self._progress = 0.0

        # Phase A: Input/Intent Pre-Flight Validation
        self._current_step = "phase_a_preflight"
        self._progress = 0.05
        await workflow.execute_activity(
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

        # Process documents via mixin
        for i, doc_readiness in enumerate(document_readiness):
            doc_id = doc_readiness["document_id"]
            
            # Check if any processing is needed
            if not all([doc_readiness["processed"], doc_readiness["extracted"], 
                       doc_readiness["enriched"], doc_readiness["indexed"]]):
                
                self._current_step = f"processing_document_{doc_id}"
                self._progress = 0.15 + (i * 0.05) if len(document_readiness) > 0 else 0.15
                
                config = DocumentProcessingConfig(
                    workflow_id=workflow_id,
                    workflow_name=workflow_name,
                    target_sections=REQUIRED_SECTIONS,
                    target_entities=REQUIRED_ENTITIES,
                    skip_processed=doc_readiness["processed"],
                    skip_extraction=doc_readiness["extracted"],
                    skip_enrichment=doc_readiness["enriched"],
                    skip_indexing=doc_readiness["indexed"]
                )
                
                await self.process_document(doc_id, config)

        # Core Quote Comparison (Phase B, Normalization, Quality, Matrix)
        self._current_step = "core_comparison"
        self._progress = 0.60
        core_result = await self._execute_core_comparison(workflow_id, document_ids)
        comparison_result = core_result.get("comparison_result")

        # Generate Insights (Reasoning)
        self._current_step = "generate_insights"
        self._progress = 0.9
        insights_result = await workflow.execute_activity(
            "generate_quote_insights_activity",
            args=[comparison_result],
            start_to_close_timeout=timedelta(minutes=2),
        )

        # Persist Result
        self._current_step = "persist_result"
        self._progress = 0.95
        persist_result = await workflow.execute_activity(
            "persist_quote_comparison_result_activity",
            args=[
                workflow_id, 
                workflow_definition_id, 
                document_ids, 
                insights_result,
                None 
            ],
            start_to_close_timeout=timedelta(seconds=60),
        )

        # Entity Comparison (Post-Processing)
        self._current_step = "entity_comparison"
        self._progress = 0.98
        await workflow.execute_activity(
            "entity_comparison_activity",
            args=[workflow_id, document_ids, metadata.get("document_names", ["Quote 1", "Quote 2"])],
            start_to_close_timeout=timedelta(minutes=2),
        )

        await workflow.execute_activity(
            "emit_workflow_event",
            args=[workflow_id, "workflow:progress", {"message": "Quote comparison completed successfully."}],
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
            "comparison_scope": core_result.get("phase_b_result", {}).get("comparison_scope", "full"),
        }

    async def _execute_core_comparison(self, workflow_id: str, document_ids: List[str]) -> Dict[str, Any]:
        """Execute core quote comparison logic (Phase B, Normalization, Quality Evaluation, and Comparison)."""
        workflow.logger.info(f"Starting core quote comparison logic for workflow {workflow_id}")

        # 1. Phase B: Capability Pre-Flight Validation
        phase_b_result = await workflow.execute_activity(
            "quote_phase_b_preflight_activity",
            args=[workflow_id, document_ids],
            start_to_close_timeout=timedelta(seconds=60),
        )

        # 2. Coverage Normalization
        await workflow.execute_activity(
            "emit_workflow_event",
            args=[workflow_id, "workflow:progress", {"message": "Normalizing coverages for comparison..."}],
            start_to_close_timeout=timedelta(seconds=10),
        )
        normalization_result = await workflow.execute_activity(
            "coverage_normalization_activity",
            args=[workflow_id, document_ids],
            start_to_close_timeout=timedelta(seconds=120),
        )

        # 3. Quality Evaluation
        await workflow.execute_activity(
            "emit_workflow_event",
            args=[workflow_id, "workflow:progress", {"message": "Evaluating quote quality and completeness..."}],
            start_to_close_timeout=timedelta(seconds=10),
        )
        quality_result = await workflow.execute_activity(
            "quality_evaluation_activity",
            args=[workflow_id, normalization_result.get("normalized_coverages", {})],
            start_to_close_timeout=timedelta(seconds=60),
        )

        # 4. Generate Side-by-Side Comparison Matrix
        await workflow.execute_activity(
            "emit_workflow_event",
            args=[workflow_id, "workflow:progress", {"message": "Generating side-by-side comparison matrix..."}],
            start_to_close_timeout=timedelta(seconds=10),
        )
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
