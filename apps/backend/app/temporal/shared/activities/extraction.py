"""LLM Extraction activities."""

from temporalio import activity
from typing import Dict, List, Optional
from uuid import UUID

from app.core.database import async_session_maker
from app.services.extracted.services.extraction.section import (
    SectionExtractionOrchestrator,
)
from app.repositories.section_chunk_repository import SectionChunkRepository
from app.repositories.section_extraction_repository import SectionExtractionRepository
from app.core.config import settings
from app.utils.logging import get_logger
from app.temporal.core.activity_registry import ActivityRegistry
from app.services.extracted.services.extraction.section.section_extraction_orchestrator import (
    SectionExtractionResult, 
    DocumentExtractionResult
)

logger = get_logger(__name__)


@ActivityRegistry.register("shared", "extract_section_fields")
@activity.defn
async def extract_section_fields(
    workflow_id: str, 
    document_id: str,
    target_sections: Optional[List[str]] = None,
    target_entities: Optional[List[str]] = None,
) -> Dict:
    """Extract section-specific fields (Legacy unified activity)."""
    # Simply call compute and then persist for backward compatibility
    result_dict = await extract_section_fields_compute(workflow_id, document_id, target_sections, target_entities)
    await persist_extraction_results(workflow_id, document_id, result_dict)
    return result_dict


@ActivityRegistry.register("shared", "extract_section_fields_compute")
@activity.defn
async def extract_section_fields_compute(
    workflow_id: str, 
    document_id: str,
    target_sections: Optional[List[str]] = None,
    target_entities: Optional[List[str]] = None,
) -> Dict:
    """Extract section-specific fields (COMPUTE ONLY) with idempotency check."""
    try:
        activity.logger.info(f"Starting section extraction compute for: {document_id}")
        
        async with async_session_maker() as session:
            # 1. READ-BEFORE-WRITE: Check if we already have results for these sections
            if target_sections and len(target_sections) == 1:
                # Optimized path: if targeting a single section, check if it already exists
                extraction_repo = SectionExtractionRepository(session)
                # Note: This is an architectural simplification for the activity. 
                # The orchestrator.extract_section_compute already does internal checks.
                pass

            # Initialize extraction orchestrator
            extraction_orchestrator = SectionExtractionOrchestrator(
                session=session,
                provider=settings.llm_provider,
                gemini_api_key=settings.gemini_api_key,
                gemini_model=settings.gemini_model,
                openrouter_api_key=settings.openrouter_api_key,
                openrouter_api_url=settings.openrouter_api_url,
                openrouter_model=settings.openrouter_model,
            )

            # 2. Fetch section super-chunks
            chunk_repo = SectionChunkRepository(session)
            super_chunks = await chunk_repo.rebuild_super_chunks(document_id=UUID(document_id))
            
            if not super_chunks:
                raise ValueError(f"No super-chunks found for document {document_id}")
            
            # Filter super-chunks if target_sections provided
            if target_sections:
                normalized_targets = [s.lower().replace(" ", "_").strip() for s in target_sections]
                super_chunks = [
                    sc for sc in super_chunks
                    if sc.section_type.value.lower().replace(" ", "_").strip() in normalized_targets
                ]
            
            if not super_chunks:
                return {"section_results": [], "all_entities": [], "metadata": {"filtered": True}}

            # 3. Perform compute-only extraction
            # extraction_orchestrator.extract_section_compute performs idempotency checks internally
            extraction_result = await extraction_orchestrator.extract_section_compute(
                super_chunks=super_chunks,
                workflow_id=UUID(workflow_id),
                document_id=UUID(document_id),
            )
            
            return extraction_result.to_dict()
            
    except Exception as e:
        activity.logger.error(f"Section extraction compute failed: {e}", exc_info=True)
        raise


@ActivityRegistry.register("shared", "persist_extraction_results")
@activity.defn
async def persist_extraction_results(
    workflow_id: str, 
    document_id: str,
    extraction_result_dict: Dict,
) -> None:
    """Persist extraction results (PERSIST ONLY)."""
    try:
        activity.logger.info(f"Persisting extraction results for: {document_id}")
        
        # Reconstruct result object from dict
        extraction_result = DocumentExtractionResult.from_dict(extraction_result_dict)
        
        async with async_session_maker() as session:
            # Initialize orchestrator for persistence logic
            extraction_orchestrator = SectionExtractionOrchestrator(session=session)
            
            await extraction_orchestrator.persist_document_extraction_result(
                document_id=UUID(document_id),
                workflow_id=UUID(workflow_id),
                extraction_result=extraction_result
            )
            
            await session.commit()
            activity.logger.info(f"Successfully persisted extraction results for {document_id}")
            
    except Exception as e:
        activity.logger.error(f"Persistence of extraction results failed: {e}", exc_info=True)
        raise
