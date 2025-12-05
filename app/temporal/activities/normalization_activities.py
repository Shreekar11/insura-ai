"""Normalization activities that wrap the existing NormalizationService.

These activities provide Temporal-compatible wrappers around:
- app/services/normalization/normalization_service.py

The NormalizationService already handles:
- Chunking via ChunkingService
- Parallel batch processing via BatchNormalizationProcessor
- Classification signals extraction
- Entity extraction per chunk
- Entity reconciliation with deterministic parser
"""

from temporalio import activity
from typing import Dict
from uuid import UUID

from app.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


@activity.defn
async def normalize_and_classify_document(document_id: str) -> Dict:
    """
    Normalize document, extract classification signals, and extract entities.
    
    Fetches OCR pages from database and performs:
    1. Chunking pages using ChunkingService
    2. Processing chunks in parallel batches using BatchNormalizationProcessor
    3. Extracting classification signals per chunk
    4. Extracting entities per chunk using LLM
    5. Detecting section types (COVERAGE, EXCLUSION, CONDITION, etc.)
    6. Reconciling entities with deterministic parser (backstop)
    7. Persisting chunks, normalized text, entities, and classification
    
    Args:
        document_id: UUID of the document to process
        
    Returns:
        Dictionary with:
        - chunk_count: Number of chunks created
        - normalized_count: Number of normalized chunks
        - entity_count: Number of entities extracted
        - classification: Document classification results
        - section_types: Section type detection statistics
    """
    try:
        activity.logger.info(f"Starting normalization for document: {document_id}")
        
        # Heartbeat to indicate activity is running
        activity.heartbeat("Starting normalization")
        
        # Import inside function to avoid sandbox issues
        from app.database.base import async_session_maker
        from app.repositories.document_repository import DocumentRepository
        from app.repositories.chunk_repository import ChunkRepository
        from app.repositories.normalization_repository import NormalizationRepository
        from app.repositories.classification_repository import ClassificationRepository
        from app.services.entity.resolver import EntityResolver
        from app.services.normalization.normalization_service import NormalizationService
        
        # Fetch OCR pages from database using document_id
        async with async_session_maker() as session:
            doc_repo = DocumentRepository(session)
            pages = await doc_repo.get_pages_by_document(UUID(document_id))
            
            if not pages:
                raise ValueError(f"No OCR pages found for document {document_id}")
            
            activity.logger.info(f"Retrieved {len(pages)} pages for normalization")
        
        # Heartbeat before processing
        activity.heartbeat(f"Processing {len(pages)} pages")
        
        # Run normalization
        async with async_session_maker() as session:
            # Initialize repositories
            chunk_repo = ChunkRepository(session)
            norm_repo = NormalizationRepository(session)
            class_repo = ClassificationRepository(session)
            entity_resolver = EntityResolver(session)
            
            # Initialize normalization service with all dependencies
            norm_service = NormalizationService(
                provider=settings.llm_provider,
                gemini_api_key=settings.gemini_api_key,
                gemini_model=settings.gemini_model,
                openrouter_api_key=settings.openrouter_api_key if settings.llm_provider == "openrouter" else None,
                openrouter_api_url=settings.openrouter_api_url,
                openrouter_model=settings.openrouter_model,
                enable_llm_fallback=settings.enable_llm_fallback,
                chunk_repository=chunk_repo,
                normalization_repository=norm_repo,
                classification_repository=class_repo,
                entity_resolver=entity_resolver,
            )
            
            activity.logger.info("Starting batch normalization and section-type detection")
            
            # Run normalization
            result, classification = await norm_service.run(
                pages=pages,
                document_id=UUID(document_id)
            )
            
            await session.commit()
        
        # Extract statistics from result
        chunk_count = len(result) if isinstance(result, list) else 0
        entity_count = 0  # Will be computed from chunks
        classification_dict = classification or {}
        
        # Get section type statistics
        section_types = {}
        if isinstance(result, list):
            for chunk in result:
                section_type = chunk.get('section_type', 'UNKNOWN')
                section_types[section_type] = section_types.get(section_type, 0) + 1
        
        activity.logger.info(
            f"Normalization complete for {document_id}: "
            f"classified as {classification_dict.get('classified_type', 'unknown')}"
        )
        
        # Log section-type detection statistics
        activity.logger.info(
            f"Section-type detection complete: {len(section_types)} unique types detected"
        )
        for section_type, count in section_types.items():
            activity.logger.info(f"  - {section_type}: {count} chunks")
        
        return {
            "chunk_count": chunk_count,
            "normalized_count": chunk_count,
            "entity_count": entity_count,
            "classification": classification_dict,
            "section_types": section_types,
        }
        
    except Exception as e:
        activity.logger.error(f"Normalization failed for {document_id}: {e}")
        raise
