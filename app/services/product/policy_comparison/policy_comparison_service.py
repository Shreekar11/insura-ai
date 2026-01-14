"""Main orchestration service for Policy Comparison workflow."""

from uuid import UUID
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.product.policy_comparison.preflight_validator import PreflightValidator
from app.services.product.policy_comparison.section_alignment_service import SectionAlignmentService
from app.services.product.policy_comparison.detailed_comparison_service import DetailedComparisonService
from app.repositories.workflow_output_repository import WorkflowOutputRepository
from app.schemas.workflows.policy_comparison import (
    PolicyComparisonResult,
    ComparisonSummary,
    ComparisonChange,
)
from app.services.product.policy_comparison.reasoning_service import PolicyComparisonReasoningService
from app.temporal.configs.policy_comparison import (
    REQUIRED_SECTIONS,
    WORKFLOW_NAME,
    WORKFLOW_VERSION,
    MINIMUM_CONFIDENCE_FOR_COMPLETION,
    MAX_HIGH_SEVERITY_CHANGES,
)
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class PolicyComparisonService:
    """Main orchestration service for Policy Comparison workflow.
    
    Coordinates the entire comparison process:
    1. Pre-flight validation
    2. Section alignment
    3. Numeric diff computation
    4. Result aggregation and persistence
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.preflight_validator = PreflightValidator(session)
        self.section_alignment_service = SectionAlignmentService(session)
        self.detailed_comparison_service = DetailedComparisonService(session)
        self.reasoning_service = PolicyComparisonReasoningService()
        self.output_repo = WorkflowOutputRepository(session)

    async def execute_comparison(
        self,
        workflow_id: UUID,
        workflow_definition_id: UUID,
        document_ids: list[UUID],
    ) -> dict:
        """Execute the complete policy comparison workflow.
        
        Args:
            workflow_id: UUID of the workflow execution
            workflow_definition_id: UUID of the workflow definition
            document_ids: List of exactly 2 document UUIDs to compare
            
        Returns:
            Dictionary with workflow execution results
        """
        LOGGER.info(
            f"Starting policy comparison for workflow {workflow_id}",
            extra={
                "workflow_id": str(workflow_id),
                "document_ids": [str(d) for d in document_ids],
            }
        )

        # Step 1: Pre-flight validation
        validation_result = await self.preflight_validator.validate_documents(
            document_ids, workflow_id
        )

        # Step 2: Section alignment
        aligned_sections = await self.section_alignment_service.align_sections(
            doc1_id=document_ids[0],
            doc2_id=document_ids[1],
            workflow_id=workflow_id,
            section_types=REQUIRED_SECTIONS,
        )

        # Step 3: Detailed comparison
        changes = await self.detailed_comparison_service.compute_comparison(
            aligned_sections=aligned_sections
        )

        # Step 4: Generate reasoning
        changes = await self.reasoning_service.enrich_changes_with_reasoning(changes)
        overall_explanation = await self.reasoning_service.generate_overall_explanation(changes)

        # Step 5: Finalize and persist result
        return await self.finalize_comparison_result(
            workflow_id=workflow_id,
            workflow_definition_id=workflow_definition_id,
            document_ids=document_ids,
            aligned_sections=aligned_sections,
            changes=changes,
            overall_explanation=overall_explanation,
            validation_result=validation_result
        )

    async def finalize_comparison_result(
        self,
        workflow_id: UUID,
        workflow_definition_id: UUID,
        document_ids: list[UUID],
        aligned_sections: list,
        changes: list[ComparisonChange],
        overall_explanation: Optional[str] = None,
        validation_result: Optional[dict] = None
    ) -> dict:
        """Finalize the comparison results and persist them to the database.
        
        This method is called by execute_comparison() or independently by Temporal activities.
        """
        # Build comparison result
        result = self._build_comparison_result(
            aligned_sections=aligned_sections,
            changes=changes,
            workflow_id=workflow_id,
            overall_explanation=overall_explanation
        )

        # Determine output status
        status = self._determine_output_status(result.comparison_summary)
        
        # Handle pre-flight validation status override
        if validation_result and not validation_result.get("validation_passed", True):
            status = "NEEDS_REVIEW"
            LOGGER.warning(
                f"Pre-flight validation failed for workflow {workflow_id}, status set to NEEDS_REVIEW"
            )

        # Persist result
        await self.output_repo.create_output(
            workflow_id=workflow_id,
            workflow_definition_id=workflow_definition_id,
            workflow_name=WORKFLOW_NAME,
            status=status,
            result=result.model_dump(mode='json'),
            confidence=result.comparison_summary.overall_confidence,
            output_metadata={
                "workflow_version": WORKFLOW_VERSION,
                "documents_compared": [str(d) for d in document_ids],
                "missing_sections": validation_result.get("missing_sections") if validation_result else None,
                "missing_entities": validation_result.get("missing_entities") if validation_result else None,
            },
        )

        await self.session.commit()

        LOGGER.info(
            f"Policy comparison finalized for workflow {workflow_id}",
            extra={
                "workflow_id": str(workflow_id),
                "status": status,
                "total_changes": result.comparison_summary.total_changes,
            }
        )

        return {
            "status": status,
            "comparison_summary": result.comparison_summary.model_dump(mode='json'),
            "total_changes": result.comparison_summary.total_changes,
        }

    def _build_comparison_result(
        self,
        aligned_sections: list,
        changes: list[ComparisonChange],
        workflow_id: UUID,
        overall_explanation: Optional[str] = None
    ) -> PolicyComparisonResult:
        """Build the complete comparison result payload.
        
        Args:
            aligned_sections: List of SectionAlignment objects
            changes: List of ComparisonChange objects
            workflow_id: Workflow UUID
            overall_explanation: Optional natural language summary
            
        Returns:
            PolicyComparisonResult object
        """
        # Calculate summary statistics
        total_changes = len(changes)
        high_severity = sum(1 for c in changes if c.severity == "high")
        medium_severity = sum(1 for c in changes if c.severity == "medium")
        low_severity = sum(1 for c in changes if c.severity == "low")

        # Calculate overall confidence (average of alignment confidences)
        if aligned_sections:
            avg_confidence = sum(a.alignment_confidence for a in aligned_sections) / len(aligned_sections)
        else:
            avg_confidence = Decimal("0.0")

        summary = ComparisonSummary(
            total_changes=total_changes,
            high_severity_changes=high_severity,
            medium_severity_changes=medium_severity,
            low_severity_changes=low_severity,
            sections_compared=len(aligned_sections),
            overall_confidence=avg_confidence,
        )

        return PolicyComparisonResult(
            comparison_summary=summary,
            changes=changes,
            section_alignments=aligned_sections,
            overall_explanation=overall_explanation,
            metadata={
                "workflow_version": WORKFLOW_VERSION,
                "workflow_id": str(workflow_id),
            },
        )

    def _determine_output_status(self, summary: ComparisonSummary) -> str:
        """Determine workflow output status based on results.
        
        Args:
            summary: ComparisonSummary object
            
        Returns:
            Status string: COMPLETED, COMPLETED_WITH_WARNINGS, or NEEDS_REVIEW
        """
        # Check if confidence is too low
        if summary.overall_confidence < MINIMUM_CONFIDENCE_FOR_COMPLETION:
            return "COMPLETED_WITH_WARNINGS"

        # Check if too many high severity changes
        if summary.high_severity_changes > MAX_HIGH_SEVERITY_CHANGES:
            return "NEEDS_REVIEW"

        # Check if there are coverage gaps or missing sections (can be extended here)
        # Note: missing sections/entities from preflight also trigger NEEDS_REVIEW
        # but the caller of this method should ideally pass that info.
        # For now, we'll check if any sections are compared at all.
        if summary.sections_compared == 0:
            return "NEEDS_REVIEW"

        return "COMPLETED"
