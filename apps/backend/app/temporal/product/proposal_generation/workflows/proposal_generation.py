"""Proposal Generation Temporal Workflow.

Orchestrates the complete proposal generation pipeline:
1. Pre-flight validation (require exactly 2 documents)
2. Document processing through shared stages via mixin
3. Proposal-specific comparison and narrative generation via child workflow
"""

from temporalio import workflow
from datetime import timedelta
from typing import Dict, List, Any

from app.temporal.shared.workflows.mixin import DocumentProcessingMixin, DocumentProcessingConfig
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
class ProposalGenerationWorkflow(DocumentProcessingMixin):
    """Temporal workflow for Proposal Generation."""

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
        """Execute the proposal generation workflow."""
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

        # Process each document via mixin
        for idx, doc_readiness in enumerate(document_readiness):
            doc_id = doc_readiness["document_id"]
            base_progress = 0.10 + (idx * 0.30)  # progress tracking
            
            # Check if any processing is needed
            if not all([doc_readiness.get("processed"), doc_readiness.get("extracted"), 
                       doc_readiness.get("enriched"), doc_readiness.get("indexed")]):
                
                self._current_step = f"processing_document_{doc_id}"
                self._progress = base_progress + 0.10
                
                config = DocumentProcessingConfig(
                    workflow_id=workflow_id,
                    target_sections=REQUIRED_SECTIONS,
                    target_entities=REQUIRED_ENTITIES,
                    skip_processed=doc_readiness.get("processed", False),
                    skip_extraction=doc_readiness.get("extracted", False),
                    skip_enrichment=doc_readiness.get("enriched", False),
                    skip_indexing=doc_readiness.get("indexed", False)
                )
                
                await self.process_document(doc_id, config)

        # Phase B: Core Proposal Generation
        self._current_step = "proposal_generation_core"
        self._progress = 0.70
        core_result = await self._execute_core_proposal_generation(
            workflow_id, document_ids, workflow_definition_id
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
            "status": core_result.get("status", "COMPLETED"),
            "workflow_id": str(workflow_id),
            "proposal_id": core_result.get("proposal_id"),
            "pdf_path": core_result.get("pdf_path"),
            "expiring_document_id": core_result.get("expiring_document_id"),
            "renewal_document_id": core_result.get("renewal_document_id"),
            "total_changes": core_result.get("total_changes", 0),
        }

    async def _execute_core_proposal_generation(
        self,
        workflow_id: str,
        document_ids: List[str],
        workflow_definition_id: str,
    ) -> Dict[str, Any]:
        """Run the core proposal generation logic locally."""
        workflow.logger.info(f"Starting core proposal generation logic for workflow {workflow_id}")

        # Step 1: Detect document roles (expiring vs. renewal)
        await workflow.execute_activity(
            "emit_workflow_event",
            args=[workflow_id, "workflow:progress", {"message": "Identifying document roles (expiring vs. renewal)..."}],
            start_to_close_timeout=timedelta(seconds=10),
        )
        roles = await workflow.execute_activity(
            "detect_document_roles_activity",
            args=[workflow_id, document_ids],
            start_to_close_timeout=timedelta(seconds=60),
        )
        
        expiring_doc_id = roles["expiring"]
        renewal_doc_id = roles["renewal"]
        
        # Step 2: Normalize coverages
        await workflow.execute_activity(
            "emit_workflow_event",
            args=[workflow_id, "workflow:progress", {"message": "Normalizing coverage data..."}],
            start_to_close_timeout=timedelta(seconds=10),
        )
        await workflow.execute_activity(
            "normalize_coverages_for_proposal_activity",
            args=[workflow_id, expiring_doc_id, renewal_doc_id],
            start_to_close_timeout=timedelta(seconds=60),
        )
        
        # Step 3: Compare documents for proposal
        await workflow.execute_activity(
            "emit_workflow_event",
            args=[workflow_id, "workflow:progress", {"message": "Comparing documents to identify key changes..."}],
            start_to_close_timeout=timedelta(seconds=10),
        )
        changes = await workflow.execute_activity(
            "compare_documents_for_proposal_activity",
            args=[workflow_id, expiring_doc_id, renewal_doc_id],
            start_to_close_timeout=timedelta(minutes=2),
        )
        
        # Step 4: Assemble proposal
        await workflow.execute_activity(
            "emit_workflow_event",
            args=[workflow_id, "workflow:progress", {"message": "Assembling final proposal..."}],
            start_to_close_timeout=timedelta(seconds=10),
        )
        proposal_data = await workflow.execute_activity(
            "assemble_proposal_activity",
            args=[{
                "workflow_id": workflow_id,
                "document_ids": document_ids,
                "changes": changes
            }],
            start_to_close_timeout=timedelta(seconds=120),
        )
        
        # Step 5: Validate proposal quality
        validation = await workflow.execute_activity(
            "validate_proposal_quality_activity",
            args=[proposal_data],
            start_to_close_timeout=timedelta(seconds=10),
        )
        
        if not validation["validation_passed"]:
            LOGGER.warning(f"Proposal validation failed for {workflow_id}: {validation['errors']}")
            await workflow.execute_activity(
                "emit_workflow_event",
                args=[workflow_id, "workflow:warning", {
                    "message": "Proposal quality check detected issues.",
                    "details": validation["errors"]
                }],
                start_to_close_timeout=timedelta(seconds=10),
            )

        # Step 6: Generate PDF
        await workflow.execute_activity(
            "emit_workflow_event",
            args=[workflow_id, "workflow:progress", {"message": "Generating proposal PDF..."}],
            start_to_close_timeout=timedelta(seconds=10),
        )
        pdf_path = await workflow.execute_activity(
            "generate_pdf_activity",
            args=[proposal_data],
            start_to_close_timeout=timedelta(minutes=3),
        )
        
        # Step 5: Persist proposal to database
        persist_result = await workflow.execute_activity(
            "persist_proposal_activity",
            args=[proposal_data, pdf_path],
            start_to_close_timeout=timedelta(seconds=60),
        )
        
        await workflow.execute_activity(
            "emit_workflow_event",
            args=[workflow_id, "workflow:progress", {"message": "Proposal generation completed successfully."}],
            start_to_close_timeout=timedelta(seconds=10),
        )
        
        return {
            "status": "COMPLETED",
            "proposal_id": persist_result.get("id"),
            "pdf_path": pdf_path,
            "expiring_document_id": expiring_doc_id,
            "renewal_document_id": renewal_doc_id,
            "total_changes": len(changes) if changes else 0,
        }
