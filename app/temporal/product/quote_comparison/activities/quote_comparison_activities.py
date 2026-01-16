"""Temporal activities for Quote Comparison workflow."""

from uuid import UUID
from temporalio import activity
from typing import Dict, List, Optional
from decimal import Decimal

from app.core.database import async_session_maker
from app.services.product.quote_comparison.quote_comparison_service import QuoteComparisonService
from app.services.product.quote_comparison.coverage_normalization_service import CoverageNormalizationService
from app.services.product.quote_comparison.coverage_quality_service import CoverageQualityService
from app.repositories.document_repository import DocumentRepository
from app.repositories.section_extraction_repository import SectionExtractionRepository
from app.repositories.workflow_repository import WorkflowDocumentStageRunRepository
from app.utils.logging import get_logger
from app.temporal.core.activity_registry import ActivityRegistry
from app.temporal.product.quote_comparison.configs.quote_comparison import (
    REQUIRED_SECTIONS,
    MIN_DOCUMENTS,
    MAX_DOCUMENTS,
)

LOGGER = get_logger(__name__)


@ActivityRegistry.register("quote_comparison", "quote_phase_a_preflight_activity")
@activity.defn
async def quote_phase_a_preflight_activity(
    workflow_id: str, 
    document_ids: list[str]
) -> dict:
    """Phase A: Input/Intent Pre-Flight Validation for Quote Comparison."""
    try:
        async with async_session_maker() as session:
            doc_repo = DocumentRepository(session)
            
            # Validate document count
            if len(document_ids) < MIN_DOCUMENTS:
                raise ValueError(
                    f"Quote comparison requires at least {MIN_DOCUMENTS} documents, "
                    f"got {len(document_ids)}"
                )
            if len(document_ids) > MAX_DOCUMENTS:
                raise ValueError(
                    f"Quote comparison supports at most {MAX_DOCUMENTS} documents, "
                    f"got {len(document_ids)}"
                )
            
            documents = []
            for doc_id in document_ids:
                doc = await doc_repo.get_by_id(UUID(doc_id))
                if not doc:
                    raise ValueError(f"Document {doc_id} not found")
                documents.append(doc)
            
            return {
                "validation_passed": True,
                "documents_validated": len(documents),
                "document_ids": document_ids,
            }
    except Exception as e:
        LOGGER.error(f"Quote Phase A pre-flight failed for workflow {workflow_id}: {e}", exc_info=True)
        raise


@ActivityRegistry.register("quote_comparison", "quote_check_document_readiness_activity")
@activity.defn
async def quote_check_document_readiness_activity(
    workflow_id: str, 
    document_ids: list[str]
) -> dict:
    """Check document readiness status for quote comparison."""
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
        LOGGER.error(
            f"Document readiness check failed for workflow {workflow_id}: {e}", 
            exc_info=True
        )
        raise


@ActivityRegistry.register("quote_comparison", "quote_phase_b_preflight_activity")
@activity.defn
async def quote_phase_b_preflight_activity(
    workflow_id: str, 
    document_ids: list[str]
) -> dict:
    """Phase B: Capability Pre-Flight Validation for Quote Comparison."""
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
            
            return {
                "validation_passed": True,  # Don't fail, allow partial comparison
                "comparison_scope": comparison_scope,
                "missing_sections": [list(m) for m in missing_sections_per_doc],
            }
    except Exception as e:
        LOGGER.error(
            f"Quote Phase B pre-flight failed for workflow {workflow_id}: {e}", 
            exc_info=True
        )
        raise


@ActivityRegistry.register("quote_comparison", "coverage_normalization_activity")
@activity.defn
async def coverage_normalization_activity(
    workflow_id: str, 
    document_ids: list[str]
) -> dict:
    """Normalize extracted coverages to canonical schema."""
    try:
        async with async_session_maker() as session:
            normalization_service = CoverageNormalizationService(session)
            
            normalized_by_doc = {}
            for doc_id in document_ids:
                coverages = await normalization_service.normalize_coverages_for_document(
                    UUID(doc_id), UUID(workflow_id)
                )
                normalized_by_doc[doc_id] = [c.model_dump(mode="json") for c in coverages]
            
            return {
                "normalized_coverages": normalized_by_doc,
                "total_coverages": sum(len(v) for v in normalized_by_doc.values()),
            }
    except Exception as e:
        LOGGER.error(
            f"Coverage normalization failed for workflow {workflow_id}: {e}", 
            exc_info=True
        )
        raise


@ActivityRegistry.register("quote_comparison", "quality_evaluation_activity")
@activity.defn
async def quality_evaluation_activity(
    workflow_id: str,
    normalized_coverages: dict
) -> dict:
    """Score each coverage using PRD quality formula."""
    try:
        from app.schemas.product.quote_comparison import CanonicalCoverage
        
        quality_service = CoverageQualityService()
        
        scores_by_doc = {}
        for doc_id, coverages_data in normalized_coverages.items():
            coverages = [CanonicalCoverage.model_validate(c) for c in coverages_data]
            scores = quality_service.evaluate_quality(coverages)
            scores_by_doc[doc_id] = [s.model_dump(mode="json") for s in scores]
        
        return {
            "quality_scores": scores_by_doc,
        }
    except Exception as e:
        LOGGER.error(
            f"Quality evaluation failed for workflow {workflow_id}: {e}", 
            exc_info=True
        )
        raise


@ActivityRegistry.register("quote_comparison", "generate_comparison_matrix_activity")
@activity.defn
async def generate_comparison_matrix_activity(
    workflow_id: str,
    document_ids: list[str]
) -> dict:
    """Generate side-by-side comparison matrix."""
    try:
        async with async_session_maker() as session:
            comparison_service = QuoteComparisonService(session)
            
            result = await comparison_service.compare_quotes(
                workflow_id=UUID(workflow_id),
                document_ids=[UUID(d) for d in document_ids]
            )
            
            return {
                "comparison_result": result.model_dump(mode="json"),
            }
    except Exception as e:
        LOGGER.error(
            f"Comparison matrix generation failed for workflow {workflow_id}: {e}", 
            exc_info=True
        )
        raise


@ActivityRegistry.register("quote_comparison", "persist_quote_comparison_result_activity")
@activity.defn
async def persist_quote_comparison_result_activity(
    workflow_id: str,
    workflow_definition_id: str,
    document_ids: list[str],
    comparison_result: dict,
    broker_summary: Optional[str] = None,
) -> dict:
    """Persist quote comparison results to WorkflowOutput."""
    try:
        from app.schemas.product.quote_comparison import QuoteComparisonResult
        
        async with async_session_maker() as session:
            comparison_service = QuoteComparisonService(session)
            
            result = QuoteComparisonResult.model_validate(comparison_result)
            
            persist_result = await comparison_service.finalize_comparison_result(
                workflow_id=UUID(workflow_id),
                workflow_definition_id=UUID(workflow_definition_id),
                document_ids=[UUID(d) for d in document_ids],
                result=result,
                broker_summary=broker_summary
            )
            
            return persist_result
    except Exception as e:
        LOGGER.error(
            f"Persist result failed for workflow {workflow_id}: {e}", 
            exc_info=True
        )
        raise
