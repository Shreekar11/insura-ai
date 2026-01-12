"""LLM Extraction activities.

These activities handle LLM extraction pipeline:
- Document classification and section mapping
- Section-level field extraction
- Cross-section validation and reconciliation
"""

from temporalio import activity
from typing import Dict, List, Optional
from uuid import UUID

from app.core.database import async_session_maker
from app.services.extracted.services.extraction.section import (
    SectionExtractionOrchestrator,
)
from app.repositories.section_chunk_repository import SectionChunkRepository
from app.repositories.workflow_repository import WorkflowRepository
from app.core.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


@activity.defn
async def extract_section_fields(
    workflow_id: str, 
    document_id: str,
    target_sections: Optional[List[str]] = None,
    target_entities: Optional[List[str]] = None,
) -> Dict:
    """Extract section-specific fields from super-chunks.
    
    This activity:
    1. Retrieves section super-chunks from database
    2. Filters super-chunks if target_sections is provided
    3. Orchestrates section-level extraction using LLM
    4. Aggregates entities across chunks
    5. Persists extracted data
    
    Args:
        workflow_id: UUID of the workflow
        document_id: UUID of the document
        target_sections: Optional list of sections to extract fields from.
        
    Returns:
        Dictionary with extraction results
    """
    try:
        activity.logger.info(
            f"Starting section extraction for: {document_id}"
        )
        activity.heartbeat("Starting section extraction")
        
        async with async_session_maker() as session:
            # Fetch section super-chunks
            chunk_repo = SectionChunkRepository(session)
            super_chunks = await chunk_repo.rebuild_super_chunks(document_id=UUID(document_id))
            
            if not super_chunks:
                raise ValueError(f"No super-chunks found for document {document_id}")
            
            # Filter super-chunks if target_sections provided
            if target_sections:
                normalized_targets = [s.lower().replace(" ", "_").strip() for s in target_sections]
                activity.logger.info(f"Filtering super-chunks for sections: {normalized_targets}")
                original_count = len(super_chunks)
                super_chunks = [
                    sc for sc in super_chunks
                    if sc.section_type.value.lower().replace(" ", "_").strip() in normalized_targets
                ]
                activity.logger.info(f"Filtered super-chunks: {original_count} -> {len(super_chunks)}")
                
                if not super_chunks:
                    activity.logger.warning(f"No super-chunks remain after filtering for {target_sections}")
                    return {"section_results": [], "all_entities": [], "metadata": {"filtered": True}}

            activity.logger.info(
                f"Retrieved {len(super_chunks)} super-chunks for extraction"
            )
            activity.heartbeat(f"Processing {len(super_chunks)} super-chunks")
            
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

            # Perform extraction
            extraction_result = await extraction_orchestrator.run(
                super_chunks=super_chunks,
                workflow_id=UUID(workflow_id),
                document_id=UUID(document_id),
            )
            
            await session.commit()
            
            activity.logger.info(
                f"Section extraction complete: "
                f"{len(extraction_result.section_results)} sections processed, "
                f"{len(extraction_result.all_entities)} entities extracted"
            )
            
            return extraction_result.to_dict()
            
    except Exception as e:
        activity.logger.error(
            f"Section extraction failed for {document_id}: {e}",
            exc_info=True
        )
        raise
