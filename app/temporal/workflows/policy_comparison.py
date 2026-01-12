"""Policy Comparison Temporal workflow.

This workflow orchestrates the complete policy comparison process using
a phased approach with conditional staged child workflow execution:

1. Phase A Pre-flight: Input/intent validation
2. Conditional Stage Execution: Ensure minimum readiness per document
3. Async Indexing Trigger: Non-blocking
4. Phase B Pre-flight: Capability validation
5. Section Alignment & Numeric Diff
6. Result Persistence
"""

from temporalio import workflow
from datetime import timedelta
from typing import Dict

from app.temporal.workflows.stages import (
    ProcessedStageWorkflow,
    ExtractedStageWorkflow,
    EnrichedStageWorkflow,
    SummarizedStageWorkflow,
)
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


@workflow.defn
class PolicyComparisonWorkflow:
    """Temporal workflow for Policy Comparison.
    
    This workflow compares two insurance policy documents using a phased,
    intent-driven approach that conditionally orchestrates staged child
    workflows to reach minimum required readiness.
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
        """Execute the policy comparison workflow.
        
        Args:
            payload: Dictionary containing:
                - workflow_id: UUID of the workflow execution
                - workflow_definition_id: UUID of the workflow definition
                - documents: List of 2 dictionaries with document_id and url
                
        Returns:
            Dictionary with comparison results
        """
        workflow_id = payload.get("workflow_id")
        workflow_definition_id = payload.get("workflow_definition_id")
        documents = payload.get("documents")

        document_ids = [doc.get("document_id") for doc in documents]

        workflow.logger.info(
            f"Starting policy comparison workflow: {workflow_id}",
            extra={"workflow_id": str(workflow_id), "document_ids": [str(d) for d in document_ids]}
        )

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

        workflow.logger.info(f"Phase A pre-flight completed: {phase_a_result}")

        # Conditional Stage Execution: Ensure Minimum Readiness
        self._current_step = "check_document_readiness"
        self._progress = 0.10

        # Check which stages are completed for each document
        readiness_result = await workflow.execute_activity(
            "check_document_readiness_activity",
            args=[workflow_id, document_ids],
            start_to_close_timeout=timedelta(seconds=30),
        )

        workflow.logger.info(f"Document readiness checked: {readiness_result}")

        # Conditionally execute staged child workflows for each document
        document_readiness = readiness_result.get("document_readiness", [])

        for doc_readiness in document_readiness:
            doc_id = doc_readiness["document_id"]
            
            workflow.logger.info(
                f"Processing document {doc_id}: "
                f"processed={doc_readiness['processed']}, "
                f"extracted={doc_readiness['extracted']}, "
                f"enriched={doc_readiness['enriched']}, "
                f"indexed={doc_readiness['indexed']}"
            )

            # Stage 1: ProcessedStageWorkflow (OCR, page analysis, chunking)
            if not doc_readiness["processed"]:
                self._current_step = f"processing_document_{doc_id}"
                self._progress = 0.15

                workflow.logger.info(f"Executing ProcessedStageWorkflow for document {doc_id}")
                
                processed_result = await workflow.execute_child_workflow(
                    ProcessedStageWorkflow.run,
                    args=[workflow_id, doc_id],
                    id=f"stage-processed-{doc_id}",
                    task_queue="documents-queue",
                )

                document_profile = processed_result.get("document_profile")

                workflow.logger.info(f"ProcessedStageWorkflow completed for document {doc_id}")

            # Stage 2: ExtractedStageWorkflow (section + entity extraction)
            if not doc_readiness["extracted"]:
                self._current_step = f"extracting_document_{doc_id}"
                self._progress = 0.20

                workflow.logger.info(f"Executing ExtractedStageWorkflow for document {doc_id}")
                
                await workflow.execute_child_workflow(
                    ExtractedStageWorkflow.run,
                    args=[workflow_id, doc_id, document_profile],  # document_profile from processed stage
                    id=f"stage-extracted-{doc_id}",
                    task_queue="documents-queue",
                )

                workflow.logger.info(f"ExtractedStageWorkflow completed for document {doc_id}")

            # Stage 3: EnrichedStageWorkflow (canonical entities, relationships)
            if not doc_readiness["enriched"]:
                self._current_step = f"enriching_document_{doc_id}"
                self._progress = 0.25

                workflow.logger.info(f"Executing EnrichedStageWorkflow for document {doc_id}")
                
                await workflow.execute_child_workflow(
                    EnrichedStageWorkflow.run,
                    args=[workflow_id, doc_id],
                    id=f"stage-enriched-{doc_id}",
                    task_queue="documents-queue",
                )

                workflow.logger.info(f"EnrichedStageWorkflow completed for document {doc_id}")

            if not doc_readiness["indexed"]:
                self._current_step = f"indexing_document_{doc_id}"
                self._progress = 0.30

                workflow.logger.info(f"Executing SummarizedStageWorkflow for document {doc_id}")
                
                await workflow.execute_child_workflow(
                    SummarizedStageWorkflow.run,
                    args=[workflow_id, doc_id],
                    id=f"stage-indexed-{doc_id}",
                    task_queue="documents-queue",
                )

                workflow.logger.info(f"SummarizedStageWorkflow completed for document {doc_id}")

        workflow.logger.info("All documents reached minimum readiness")


        # Phase B: Capability Pre-Flight Validation
        self._current_step = "phase_b_preflight"
        self._progress = 0.45

        phase_b_result = await workflow.execute_activity(
            "phase_b_preflight_activity",
            args=[workflow_id, document_ids],
            start_to_close_timeout=timedelta(seconds=60),
        )

        workflow.logger.info(f"Phase B pre-flight completed: {phase_b_result}")

        # Section Alignment
        self._current_step = "section_alignment"
        self._progress = 0.60

        alignment_result = await workflow.execute_activity(
            "section_alignment_activity",
            args=[workflow_id, document_ids],
            start_to_close_timeout=timedelta(seconds=120),
        )

        workflow.logger.info(f"Section alignment completed: {alignment_result}")

        # Numeric Diff Computation
        self._current_step = "numeric_diff"
        self._progress = 0.75

        diff_result = await workflow.execute_activity(
            "numeric_diff_activity",
            args=[workflow_id, alignment_result],
            start_to_close_timeout=timedelta(seconds=120),
        )

        workflow.logger.info(f"Numeric diff completed: {diff_result}")

        # Persist Comparison Result
        self._current_step = "persist_result"
        self._progress = 0.90

        persist_result = await workflow.execute_activity(
            "persist_comparison_result_activity",
            args=[workflow_id, workflow_definition_id, document_ids, alignment_result, diff_result],
            start_to_close_timeout=timedelta(seconds=60),
        )

        workflow.logger.info(f"Result persisted: {persist_result}")

        # Complete
        self._status = "completed"
        self._progress = 1.0
        self._current_step = "completed"

        return {
            "status": "completed",
            "workflow_id": str(workflow_id),
            "comparison_summary": persist_result.get("comparison_summary"),
            "total_changes": persist_result.get("total_changes"),
            "comparison_scope": phase_b_result.get("comparison_scope", "full"),
        }

