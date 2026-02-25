"""Temporal activities for Policy Comparison workflow"""

from uuid import UUID
from temporalio import activity
from typing import Dict, List, Optional
from decimal import Decimal

from app.core.database import async_session_maker
from app.services.product.policy_comparison.policy_comparison_service import PolicyComparisonService
from app.repositories.document_repository import DocumentRepository
from app.repositories.section_extraction_repository import SectionExtractionRepository
from app.repositories.workflow_repository import WorkflowDocumentRepository, WorkflowDocumentStageRunRepository 
from app.utils.logging import get_logger
from app.temporal.core.activity_registry import ActivityRegistry
from app.temporal.product.policy_comparison.configs.policy_comparison import REQUIRED_SECTIONS
from app.services.product.policy_comparison.section_alignment_service import SectionAlignmentService
from app.services.product.policy_comparison.detailed_comparison_service import DetailedComparisonService
from app.services.product.policy_comparison.reasoning_service import PolicyComparisonReasoningService

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

@ActivityRegistry.register("policy_comparison", "policy_entity_comparison_activity")
@activity.defn
async def policy_entity_comparison_activity(
    workflow_id: str,
    document_ids: list[str],
    document_names: list[str],
) -> dict:
    """Execute entity comparison and emit comparison:completed event.
    
    This activity:
    1. Retrieves extracted data for both documents
    2. Performs entity-level comparison (coverages & exclusions)
    3. Emits comparison:completed SSE event
    4. Stores results in workflow output for API retrieval
    """
    try:
        async with async_session_maker() as session:
            from app.repositories.step_repository import (
                StepEntityOutputRepository,
                StepSectionOutputRepository,
            )
            from app.repositories.workflow_output_repository import WorkflowOutputRepository
            
            step_entity_repo = StepEntityOutputRepository(session)
            step_section_repo = StepSectionOutputRepository(session)
            output_repo = WorkflowOutputRepository(session)
            
            # Get extracted data for both documents
            doc1_data = await _get_extracted_data_for_comparison(
                step_entity_repo, step_section_repo, document_ids[0], workflow_id
            )
            doc2_data = await _get_extracted_data_for_comparison(
                step_entity_repo, step_section_repo, document_ids[1], workflow_id
            )
            
            LOGGER.info(
                f"Entity comparison: doc1 has {len(doc1_data.get('entities', []))} entities, "
                f"doc2 has {len(doc2_data.get('entities', []))} entities"
            )
            
            # Execute entity comparison (which also emits SSE event)
            comparison_service = PolicyComparisonService(session)
            result = await comparison_service.execute_entity_comparison(
                workflow_id=UUID(workflow_id),
                doc1_id=UUID(document_ids[0]),
                doc2_id=UUID(document_ids[1]),
                doc1_data=doc1_data,
                doc2_data=doc2_data,
                doc1_name=document_names[0],
                doc2_name=document_names[1],
            )
            
            # Store entity comparison in workflow output for API retrieval
            await output_repo.update_entity_comparison(
                workflow_id=UUID(workflow_id),
                entity_comparison=result.model_dump(mode="json"),
            )
            await session.commit()
            
            LOGGER.info(
                f"Entity comparison completed for workflow {workflow_id}: "
                f"{len(result.comparisons)} comparisons"
            )
            
            return {
                "status": "completed",
                "total_comparisons": len(result.comparisons),
                "coverage_matches": result.summary.coverage_matches,
                "exclusion_matches": result.summary.exclusion_matches,
            }
    except Exception as e:
        LOGGER.error(f"Entity comparison failed for workflow {workflow_id}: {e}", exc_info=True)
        raise


@ActivityRegistry.register("policy_comparison", "section_alignment_activity")
@activity.defn
async def section_alignment_activity(workflow_id: str, document_ids: list[str]) -> list:
    """Align sections across two documents."""
    try:
        async with async_session_maker() as session:
            alignment_service = SectionAlignmentService(session)
            alignments = await alignment_service.align_sections(
                doc1_id=UUID(document_ids[0]),
                doc2_id=UUID(document_ids[1]),
                workflow_id=UUID(workflow_id),
                section_types=REQUIRED_SECTIONS,
            )
            return [a.model_dump(mode="json") for a in alignments]
    except Exception as e:
        LOGGER.error(f"Section alignment failed for workflow {workflow_id}: {e}", exc_info=True)
        raise


@ActivityRegistry.register("policy_comparison", "detailed_comparison_activity")
@activity.defn
async def detailed_comparison_activity(workflow_id: str, aligned_sections: list) -> list:
    """Compute detailed differences for aligned sections."""
    try:
        from app.schemas.product.policy_comparison import SectionAlignment
        
        async with async_session_maker() as session:
            comparison_service = DetailedComparisonService(session)
            
            alignments = [SectionAlignment(**a) for a in aligned_sections]
            
            changes = await comparison_service.compute_comparison(
                aligned_sections=alignments
            )
            
            return [c.model_dump(mode="json") for c in changes]
    except Exception as e:
        LOGGER.error(f"Detailed comparison failed for workflow {workflow_id}: {e}", exc_info=True)
        raise


@ActivityRegistry.register("policy_comparison", "generate_comparison_reasoning_activity")
@activity.defn
async def generate_comparison_reasoning_activity(workflow_id: str, changes_data: list) -> dict:
    """Enrich changes with reasoning and generate overall explanation."""
    try:
        from app.schemas.product.policy_comparison import ComparisonChange
        
        async with async_session_maker() as session:
            reasoning_service = PolicyComparisonReasoningService()
            
            # Reconstruct ComparisonChange objects
            changes = [ComparisonChange(**c) for c in changes_data]
            
            enriched_changes = await reasoning_service.enrich_changes_with_reasoning(changes)
            overall_explanation = await reasoning_service.generate_overall_explanation(enriched_changes)
            
            return {
                "enriched_changes": [c.model_dump(mode="json") for c in enriched_changes],
                "overall_explanation": overall_explanation,
            }
    except Exception as e:
        LOGGER.error(f"Reasoning generation failed for workflow {workflow_id}: {e}", exc_info=True)
        raise


@ActivityRegistry.register("policy_comparison", "persist_comparison_result_activity")
@activity.defn
async def persist_comparison_result_activity(
    workflow_id: str,
    workflow_definition_id: str,
    document_ids: list[str],
    alignment_data: list,
    reasoning_data: dict,
    phase_b_result: dict,
) -> dict:
    """Finalize and persist comparison results."""
    try:
        from app.schemas.product.policy_comparison import SectionAlignment, ComparisonChange
        
        async with async_session_maker() as session:
            comparison_service = PolicyComparisonService(session)
            
            # Reconstruct objects
            alignments = [SectionAlignment(**a) for a in alignment_data]
            changes = [ComparisonChange(**c) for c in reasoning_data.get("enriched_changes", [])]
            overall_explanation = reasoning_data.get("overall_explanation")
            
            result = await comparison_service.finalize_comparison_result(
                workflow_id=UUID(workflow_id),
                workflow_definition_id=UUID(workflow_definition_id),
                document_ids=[UUID(d) for d in document_ids],
                aligned_sections=alignments,
                changes=changes,
                overall_explanation=overall_explanation,
                validation_result=phase_b_result
            )
            
            return result
    except Exception as e:
        LOGGER.error(f"Persisting comparison result failed for workflow {workflow_id}: {e}", exc_info=True)
        raise


async def _get_extracted_data_for_comparison(
    step_entity_repo,
    step_section_repo,
    document_id: str,
    workflow_id: str,
) -> dict:
    """Get extracted entity and section data for a document.
    
    Returns data in format expected by EntityComparisonService.
    """
    entities = await step_entity_repo.get_by_document_and_workflow(
        UUID(document_id), UUID(workflow_id)
    )
    sections = await step_section_repo.get_by_document_and_workflow(
        UUID(document_id), UUID(workflow_id)
    )
    
    # Extract coverages and exclusions from entities
    coverages = []
    exclusions = []
    
    for entity in entities:
        if not entity.display_payload:
            continue
            
        payload = entity.display_payload
        
        if entity.entity_type.lower() == "coverage":
            if isinstance(payload, list):
                coverages.extend(payload)
            elif isinstance(payload, dict):
                coverages.append(payload)
        elif entity.entity_type.lower() == "exclusion":
            if isinstance(payload, list):
                exclusions.extend(payload)
            elif isinstance(payload, dict):
                exclusions.append(payload)
    
    # Also check sections for effective_coverages/exclusions
    for section in sections:
        if not section.display_payload:
            continue
            
        payload = section.display_payload
        
        # Unpack modifications and provisions if they exist
        if isinstance(payload, dict):
            if "modifications" in payload and isinstance(payload["modifications"], list):
                for mod in payload["modifications"]:
                    # Tag with extraction source info
                    mod["_extraction_id"] = str(section.id)
                    mod["_section_type"] = section.section_type
                    
                    # Flatten attributes for better matching
                    if "attributes" in mod and isinstance(mod["attributes"], dict):
                        for k, v in mod["attributes"].items():
                            if k not in mod:
                                mod[k] = v
                                
                    if "impacted_coverage" in mod:
                        coverages.append(mod)
                    elif "impacted_exclusion" in mod:
                        exclusions.append(mod)
                    else:
                        coverages.append(mod)

            if "provisions" in payload and isinstance(payload["provisions"], list):
                for prov in payload["provisions"]:
                    prov["_extraction_id"] = str(section.id)
                    prov["_section_type"] = section.section_type
                    
                    # Flatten attributes 
                    if "attributes" in prov and isinstance(prov["attributes"], dict):
                        for k, v in prov["attributes"].items():
                            if k not in prov:
                                prov[k] = v
                                
                    # Map provision_name to coverage_name for the matcher
                    if "provision_name" in prov and "coverage_name" not in prov:
                        prov["coverage_name"] = prov["provision_name"]
                    
                    if "impacted_coverage" in prov:
                        coverages.append(prov)
                    elif "impacted_exclusion" in prov:
                        exclusions.append(prov)
                    else:
                        coverages.append(prov)

        if section.section_type == "effective_coverages":
            if isinstance(payload, list):
                coverages.extend(payload)
            elif isinstance(payload, dict):
                coverages.append(payload)
        elif section.section_type == "effective_exclusions":
            if isinstance(payload, list):
                exclusions.extend(payload)
            elif isinstance(payload, dict):
                exclusions.append(payload)
    
    return {
        "entities": [e.display_payload for e in entities if e.display_payload],
        "section_results": [
            {
                "section_type": s.section_type,
                "extracted_data": s.display_payload,
                "extraction_id": str(s.id),
                "confidence": float(s.confidence.get("overall", 0.0)) if isinstance(s.confidence, dict) else (float(s.confidence) if s.confidence else None),
                "page_numbers": s.page_numbers if hasattr(s, "page_numbers") else None,
            }
            for s in sections if s.display_payload
        ],
        "effective_coverages": coverages,
        "effective_exclusions": exclusions,
    }
