"""LLM Extraction activities.

These activities handle LLM extraction pipeline:
- Document classification and section mapping
- Section-level field extraction
- Cross-section validation and reconciliation
"""

from temporalio import activity
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from app.database.base import async_session_maker
from app.database.models import Workflow
from app.services.extracted.services.extraction.section import (
    SectionExtractionOrchestrator,
)
from app.repositories.section_chunk_repository import SectionChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


def _get_timeout_for_provider(provider: str, default_timeout: int, ollama_timeout: int) -> int:
    """Get timeout value based on provider.
    
    Ollama models running locally typically need more time to process requests,
    so we use higher timeout values for Ollama provider.
    
    Args:
        provider: LLM provider name ("gemini", "openrouter", "ollama")
        default_timeout: Default timeout in seconds for non-Ollama providers
        ollama_timeout: Timeout in seconds for Ollama provider
        
    Returns:
        Timeout value in seconds
    """
    if provider.lower() == "ollama":
        return ollama_timeout
    return default_timeout


def _normalize_section_type(section_type_str: Optional[str]) -> str:
    """Normalize section type string to canonical SectionType enum value.
    
    Uses SectionTypeMapper to ensure consistent taxonomy across the pipeline.
    Maps alternative section type strings to their canonical SectionType values.
    For example, "sov" maps to "schedule_of_values", "endorsement" maps to "endorsements".
    
    Args:
        section_type_str: Section type string to normalize (can be None)
        
    Returns:
        Normalized section type string that matches a SectionType enum value
    """
    if not section_type_str:
        return "unknown"
    
    from app.utils.section_type_mapper import SectionTypeMapper
    
    # Use canonical mapper to normalize
    section_type = SectionTypeMapper.string_to_section_type(section_type_str)
    return section_type.value


@activity.defn
async def extract_section_fields(document_id: str, classification_result: Dict) -> Dict:
    """Extract section-specific fields from super-chunks.
    
    This activity:
    1. Retrieves section super-chunks from database
    2. Orchestrates section-level extraction using LLM
    3. Aggregates entities across chunks
    4. Persists extracted data
    
    Args:
        document_id: UUID of the document to extract from
        classification_result: Classification result
        
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
            super_chunks = await chunk_repo.rebuild_super_chunks(UUID(document_id))
            
            if not super_chunks:
                raise ValueError(f"No super-chunks found for document {document_id}")
            
            activity.logger.info(
                f"Retrieved {len(super_chunks)} super-chunks for extraction"
            )
            activity.heartbeat(f"Processing {len(super_chunks)} super-chunks")
            
            # Determine timeout based on provider (Ollama needs more time for local models)
            extraction_timeout = _get_timeout_for_provider(
                provider=settings.llm_provider,
                default_timeout=120,  # 2 minutes default
                ollama_timeout=300,  # 5 minutes for Ollama
            )
            
            activity.logger.info(
                f"Using timeout: {extraction_timeout}s "
                f"(provider: {settings.llm_provider})"
            )
            
            # Initialize extraction orchestrator
            extraction_orchestrator = SectionExtractionOrchestrator(
                session=session,
                provider=settings.llm_provider,
                gemini_api_key=settings.gemini_api_key,
                gemini_model=settings.gemini_model,
                openrouter_api_key=settings.openrouter_api_key,
                openrouter_api_url=settings.openrouter_api_url,
                openrouter_model=settings.openrouter_model,
                timeout=extraction_timeout,
            )
            
            # Fetch active workflow ID
            stmt = select(Workflow).where(
                Workflow.document_id == UUID(document_id)
            ).order_by(Workflow.created_at.desc()).limit(1)
            
            workflow_result = await session.execute(stmt)
            workflow_obj = workflow_result.scalar_one_or_none()
            workflow_id_uuid = workflow_obj.id if workflow_obj else None
            
            if not workflow_id_uuid:
                activity.logger.warning(
                    f"No active workflow found for document {document_id}, step outputs will not be persisted"
                )

            # Perform extraction
            extraction_result = await extraction_orchestrator.run(
                super_chunks=super_chunks,
                document_id=UUID(document_id),
                workflow_id=workflow_id_uuid,
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
