import asyncio
from datetime import timedelta
from typing import List, Dict, Any
from uuid import UUID
from temporalio import activity

from app.core.database import get_async_session_context
from app.services.workflow_service import WorkflowService
from app.services.product.policy_comparison.policy_comparison_service import PolicyComparisonService
from app.repositories.workflow_output_repository import WorkflowOutputRepository
from app.services.sse_manager import SSEManager
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)

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
        "sections": [s.display_payload for s in sections if s.display_payload],
        "effective_coverages": coverages,
        "effective_exclusions": exclusions,
    }

@activity.defn
async def entity_comparison_activity(
    workflow_id: str,
    document_ids: List[str],
    document_names: List[str]
) -> Dict[str, Any]:
    """
    Execute entity-level comparison for quote documents.
    
    This reuses the PolicyComparisonService logic as the underlying entity comparison 
    (coverages vs coverages) is the same for both policies and quotes.
    
    Args:
        workflow_id: The workflow execution ID
        document_ids: List of 2 document IDs to compare
        document_names: List of names for the documents
        
    Returns:
        Dict containing the comparison result
    """
    LOGGER.info(f"Starting entity comparison for workflow: {workflow_id}")
    
    # Emit start event
    sse_manager = SSEManager()
    await sse_manager.emit_status_update(
        workflow_id=UUID(workflow_id),
        status="processing",
        message="Running entity-level comparison...",
        step="entity_comparison",
        progress=0.9
    )

    try:
        async with get_async_session_context() as session:
            # Initialize services and repos
            workflow_service = WorkflowService(session)
            
            comparison_service = PolicyComparisonService(session)
            output_repo = WorkflowOutputRepository(session)
            
            # Fetch data using the helper
            doc1_data = await _get_extracted_data_for_comparison(
                workflow_service.step_entity_output_repo,
                workflow_service.step_section_output_repo,
                document_ids[0],
                workflow_id
            )
            
            doc2_data = await _get_extracted_data_for_comparison(
                workflow_service.step_entity_output_repo,
                workflow_service.step_section_output_repo,
                document_ids[1],
                workflow_id
            )
            
            # Execute comparison
            result = await comparison_service.execute_entity_comparison(
                workflow_id=UUID(workflow_id),
                doc1_id=UUID(document_ids[0]),
                doc2_id=UUID(document_ids[1]),
                doc1_data=doc1_data,
                doc2_data=doc2_data,
                doc1_name=document_names[0],
                doc2_name=document_names[1],
            )
            
            # Store in output metadata
            await output_repo.update_entity_comparison(
                workflow_id=UUID(workflow_id),
                entity_comparison=result.model_dump(mode="json"),
            )
            await session.commit()
            
            LOGGER.info(
                f"Entity comparison completed for workflow {workflow_id}: "
                f"{len(result.comparisons)} comparisons"
            )

            # Emit completion event
            await sse_manager.emit_status_update(
                workflow_id=UUID(workflow_id),
                status="processing",
                message="Entity comparison completed",
                step="entity_comparison",
                progress=0.95
            )

            return {
                "status": "completed",
                "total_comparisons": len(result.comparisons),
                "coverage_matches": result.summary.coverage_matches,
                "exclusion_matches": result.summary.exclusion_matches,
            }

    except Exception as e:
        LOGGER.error(f"Entity comparison failed for workflow {workflow_id}: {e}", exc_info=True)
        # Emit failure event?
        raise
