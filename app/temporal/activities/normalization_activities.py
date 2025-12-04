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

from app.services.normalization.normalization_service import NormalizationService
from app.utils.logging import get_logger

logger = get_logger(__name__)


@activity.defn
async def normalize_and_classify_document(document_id: str) -> Dict:
    """
    Normalize document, extract classification signals, and extract entities.
    
    This wraps the existing NormalizationService.run() method which performs:
    1. Chunking pages using ChunkingService
    2. Processing chunks in parallel batches using BatchNormalizationProcessor
    3. Extracting classification signals per chunk
    4. Extracting entities per chunk using LLM
    5. Reconciling entities with deterministic parser (backstop)
    6. Persisting chunks, normalized text, entities, and classification
    
    Args:
        document_id: UUID of the document to process
        
    Returns:
        Dictionary with:
        - chunk_count: Number of chunks created
        - normalized_count: Number of normalized chunks
        - entity_count: Number of entities extracted
        - classification: Document classification results
    """
    try:
        activity.logger.info(f"Starting normalization for document: {document_id}")
        
        # Heartbeat to indicate activity is running
        activity.heartbeat("Starting normalization")
        
        # Get OCR pages from database
        from app.database.session import get_session
        async with get_session() as session:
            from app.repositories.ocr_repository import OCRRepository
            ocr_repo = OCRRepository(session)
            pages = await ocr_repo.get_pages_by_document(UUID(document_id))
            
            if not pages:
                raise ValueError(f"No OCR pages found for document {document_id}")
            
            activity.logger.info(f"Retrieved {len(pages)} OCR pages for normalization")
        
        # Heartbeat after retrieving pages
        activity.heartbeat(f"Processing {len(pages)} pages")
        
        # Use existing normalization service
        async with get_session() as session:
            norm_service = NormalizationService(db_session=session)
            
            # Run normalization (this handles everything)
            result = await norm_service.run(
                pages=pages,
                document_id=UUID(document_id)
            )
        
        # Extract statistics from result
        chunk_count = len(result.get('chunks', []))
        entity_count = result.get('entity_count', 0)
        classification = result.get('classification', {})
        
        activity.logger.info(
            f"Normalization complete for {document_id}: "
            f"{chunk_count} chunks, {entity_count} entities, "
            f"classified as {classification.get('classified_type', 'unknown')}"
        )
        
        return {
            "chunk_count": chunk_count,
            "normalized_count": chunk_count,  # Same as chunk_count
            "entity_count": entity_count,
            "classification": classification,
        }
        
    except Exception as e:
        activity.logger.error(f"Normalization failed for {document_id}: {e}")
        raise
