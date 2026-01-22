"""Temporal activities for Policy Comparison workflow"""

from uuid import UUID
from temporalio import activity
from typing import Dict, List, Optional
from decimal import Decimal

from app.core.database import async_session_maker
from app.services.product.policy_comparison.policy_comparison_service import PolicyComparisonService
from app.services.product.policy_comparison.section_alignment_service import SectionAlignmentService
from app.services.product.policy_comparison.detailed_comparison_service import DetailedComparisonService
from app.services.product.policy_comparison.reasoning_service import PolicyComparisonReasoningService
from app.schemas.product.policy_comparison import SectionAlignment, ComparisonChange, SectionProvenance
from app.repositories.document_repository import DocumentRepository
from app.repositories.section_extraction_repository import SectionExtractionRepository
from app.repositories.workflow_repository import WorkflowDocumentRepository, WorkflowDocumentStageRunRepository 
from app.utils.logging import get_logger
from app.temporal.core.activity_registry import ActivityRegistry
from app.temporal.product.policy_comparison.configs.policy_comparison import REQUIRED_SECTIONS

LOGGER = get_logger(__name__)

@ActivityRegistry.register("policy_comparison", "phase_a_preflight_activity")
@activity.defn
async def phase_a_preflight_activity(workflow_id: str, document_ids: list[str]) -> dict:
    """Phase A: Input/Intent Pre-Flight Validation."""
    try:
        async with async_session_maker() as session:
            doc_repo = DocumentRepository(session)
            if len(document_ids) != 2:
                raise ValueError(f"Policy comparison requires exactly 2 documents, got {len(document_ids)}")

            documents = []
            for doc_id in document_ids:
                doc = await doc_repo.get_by_id(UUID(doc_id))
                if not doc:
                    raise ValueError(f"Document {doc_id} not found")
                documents.append(doc)

            return {
                "validation_passed": True,
                "documents_validated": len(documents),
            }
    except Exception as e:
        LOGGER.error(f"Phase A pre-flight failed for workflow {workflow_id}: {e}", exc_info=True)
        raise


@ActivityRegistry.register("policy_comparison", "check_document_readiness_activity")
@activity.defn
async def check_document_readiness_activity(workflow_id: str, document_ids: list[str]) -> dict:
    """Check document readiness status for comparison."""
    try:
        async with async_session_maker() as session:
            stage_repo = WorkflowDocumentStageRunRepository(session)
            document_readiness = []

            for doc_id in document_ids:
                stages = await stage_repo.get_by_workflow_and_document(
                    UUID(workflow_id), UUID(doc_id)
                )

                stage_status = {
                    "processed": False,
                    "extracted": False,
                    "enriched": False,
                    "indexed": False,
                }

                for stage in stages:
                    if stage.stage_name in stage_status and stage.status == "completed":
                        stage_status[stage.stage_name] = True

                document_readiness.append({
                    "document_id": doc_id,
                    **stage_status
                })

            return {
                "document_readiness": document_readiness,
            }
    except Exception as e:
        LOGGER.error(f"Document readiness check failed for workflow {workflow_id}: {e}", exc_info=True)
        raise


@ActivityRegistry.register("policy_comparison", "phase_b_preflight_activity")
@activity.defn
async def phase_b_preflight_activity(workflow_id: str, document_ids: list[str]) -> dict:
    """Phase B: Capability Pre-Flight Validation."""
    try:
        async with async_session_maker() as session:
            section_repo = SectionExtractionRepository(session)
            missing_sections_per_doc = []
            for doc_id in document_ids:
                sections = await section_repo.get_by_document_and_workflow(
                    UUID(doc_id), UUID(workflow_id)
                )
                section_types = {s.section_type for s in sections}
                missing = set(REQUIRED_SECTIONS) - section_types
                missing_sections_per_doc.append(missing)

            missing_any = any(len(missing) > 0 for missing in missing_sections_per_doc)
            comparison_scope = "full" if not missing_any else "partial"
            validation_passed = not missing_any

            return {
                "validation_passed": validation_passed,
                "comparison_scope": comparison_scope,
                "missing_sections": [list(m) for m in missing_sections_per_doc],
            }
    except Exception as e:
        LOGGER.error(f"Phase B pre-flight failed for workflow {workflow_id}: {e}", exc_info=True)
        raise


@ActivityRegistry.register("policy_comparison", "section_alignment_activity")
@activity.defn
async def section_alignment_activity(workflow_id: str, document_ids: list[str]) -> dict:
    """Temporal activity for section alignment."""
    try:
        async with async_session_maker() as session:
            alignment_service = SectionAlignmentService(session)
            alignments = await alignment_service.align_sections(
                doc1_id=UUID(document_ids[0]),
                doc2_id=UUID(document_ids[1]),
                workflow_id=UUID(workflow_id),
                section_types=REQUIRED_SECTIONS,
            )

            return {
                "alignments": [
                    {
                        "section_type": a.section_type,
                        "doc1_section_id": str(a.doc1_section_id),
                        "doc2_section_id": str(a.doc2_section_id),
                        "alignment_confidence": float(a.alignment_confidence),
                        "alignment_method": a.alignment_method,
                    }
                    for a in alignments
                ],
                "alignment_count": len(alignments),
            }
    except Exception as e:
        LOGGER.error(f"Section alignment failed for workflow {workflow_id}: {e}", exc_info=True)
        raise


@ActivityRegistry.register("policy_comparison", "detailed_comparison_activity")
@activity.defn
async def detailed_comparison_activity(workflow_id: str, alignment_result: dict) -> dict:
    """Temporal activity for detailed comparison."""
    try:
        async with async_session_maker() as session:
            diff_service = DetailedComparisonService(session)
            alignments = [
                SectionAlignment(
                    section_type=a["section_type"],
                    doc1_section_id=UUID(a["doc1_section_id"]),
                    doc2_section_id=UUID(a["doc2_section_id"]),
                    alignment_confidence=Decimal(str(a["alignment_confidence"])),
                    alignment_method=a.get("alignment_method"),
                )
                for a in alignment_result["alignments"]
            ]

            changes = await diff_service.compute_comparison(aligned_sections=alignments)

            def sanitize(val):
                if isinstance(val, Decimal):
                    return float(val)
                return val

            return {
                "changes": [
                    {
                        "field_name": c.field_name,
                        "section_type": c.section_type,
                        "coverage_name": c.coverage_name,
                        "old_value": sanitize(c.old_value),
                        "new_value": sanitize(c.new_value),
                        "change_type": c.change_type,
                        "percent_change": float(c.percent_change) if c.percent_change is not None else None,
                        "absolute_change": float(c.absolute_change) if c.absolute_change is not None else None,
                        "severity": c.severity,
                        "provenance": {
                            "doc1_section_id": str(c.provenance.doc1_section_id),
                            "doc2_section_id": str(c.provenance.doc2_section_id),
                            "doc1_page_range": c.provenance.doc1_page_range,
                            "doc2_page_range": c.provenance.doc2_page_range,
                        },
                    }
                    for c in changes
                ],
                "change_count": len(changes),
            }
    except Exception as e:
        LOGGER.error(f"Detailed comparison failed for workflow {workflow_id}: {e}", exc_info=True)
        raise


@ActivityRegistry.register("policy_comparison", "generate_comparison_reasoning_activity")
@activity.defn
async def generate_comparison_reasoning_activity(workflow_id: str, diff_result: dict) -> dict:
    """Temporal activity for generating natural language reasoning."""
    try:
        reasoning_service = PolicyComparisonReasoningService()
        changes = []
        for c in diff_result["changes"]:
            changes.append(
                ComparisonChange(
                    field_name=c["field_name"],
                    section_type=c["section_type"],
                    coverage_name=c.get("coverage_name"),
                    old_value=c["old_value"],
                    new_value=c["new_value"],
                    change_type=c["change_type"],
                    percent_change=c.get("percent_change"),
                    absolute_change=c.get("absolute_change"),
                    severity=c["severity"],
                    provenance=SectionProvenance(
                        doc1_section_id=UUID(c["provenance"]["doc1_section_id"]),
                        doc2_section_id=UUID(c["provenance"]["doc2_section_id"]),
                        doc1_page_range=c["provenance"]["doc1_page_range"],
                        doc2_page_range=c["provenance"]["doc2_page_range"],
                    ),
                )
            )

        enriched_changes = await reasoning_service.enrich_changes_with_reasoning(changes)
        overall_explanation = await reasoning_service.generate_overall_explanation(enriched_changes)

        def sanitize(val):
            if isinstance(val, Decimal):
                return float(val)
            return val

        return {
            "changes": [
                {
                    "field_name": c.field_name,
                    "section_type": c.section_type,
                    "coverage_name": c.coverage_name,
                    "old_value": sanitize(c.old_value),
                    "new_value": sanitize(c.new_value),
                    "change_type": c.change_type,
                    "percent_change": float(c.percent_change) if c.percent_change is not None else None,
                    "absolute_change": float(c.absolute_change) if c.absolute_change is not None else None,
                    "severity": c.severity,
                    "provenance": {
                        "doc1_section_id": str(c.provenance.doc1_section_id),
                        "doc2_section_id": str(c.provenance.doc2_section_id),
                        "doc1_page_range": c.provenance.doc1_page_range,
                        "doc2_page_range": c.provenance.doc2_page_range,
                    },
                    "reasoning": c.reasoning
                }
                for c in enriched_changes
            ],
            "overall_explanation": overall_explanation
        }
    except Exception as e:
        LOGGER.error(f"Reasoning activity failed for workflow {workflow_id}: {e}", exc_info=True)
        raise


@ActivityRegistry.register("policy_comparison", "persist_comparison_result_activity")
@activity.defn
async def persist_comparison_result_activity(
    workflow_id: str,
    workflow_definition_id: str,
    document_ids: list[str],
    alignment_result: dict,
    reasoning_result: dict,
    phase_b_result: Optional[dict] = None,
) -> dict:
    """Temporal activity for persisting comparison results."""
    try:
        async with async_session_maker() as session:
            comparison_service = PolicyComparisonService(session)
            alignments = [
                SectionAlignment(
                    section_type=a["section_type"],
                    doc1_section_id=UUID(a["doc1_section_id"]),
                    doc2_section_id=UUID(a["doc2_section_id"]),
                    alignment_confidence=Decimal(str(a["alignment_confidence"])),
                    alignment_method=a.get("alignment_method"),
                )
                for a in alignment_result["alignments"]
            ]

            changes = [
                ComparisonChange(
                    field_name=c["field_name"],
                    section_type=c["section_type"],
                    coverage_name=c.get("coverage_name"),
                    old_value=c["old_value"],
                    new_value=c["new_value"],
                    change_type=c["change_type"],
                    percent_change=Decimal(str(c["percent_change"])) if c.get("percent_change") is not None else None,
                    absolute_change=Decimal(str(c["absolute_change"])) if c.get("absolute_change") is not None else None,
                    severity=c["severity"],
                    provenance=SectionProvenance(
                        doc1_section_id=UUID(c["provenance"]["doc1_section_id"]),
                        doc2_section_id=UUID(c["provenance"]["doc2_section_id"]),
                        doc1_page_range=c["provenance"]["doc1_page_range"],
                        doc2_page_range=c["provenance"]["doc2_page_range"],
                    ),
                    reasoning=c.get("reasoning")
                )
                for c in reasoning_result["changes"]
            ]

            result = await comparison_service.finalize_comparison_result(
                workflow_id=UUID(workflow_id),
                workflow_definition_id=UUID(workflow_definition_id),
                document_ids=[UUID(d) for d in document_ids],
                aligned_sections=alignments,
                changes=changes,
                overall_explanation=reasoning_result.get("overall_explanation"),
                validation_result=phase_b_result
            )

            return result
    except Exception as e:
        LOGGER.error(f"Persist result failed for workflow {workflow_id}: {e}", exc_info=True)
        raise
