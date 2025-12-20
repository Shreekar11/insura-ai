"""Normalization activities for Phase 2.

These activities handle chunking and LLM-based normalization.
"""

from temporalio import activity
from typing import Dict
from uuid import UUID

from app.database.base import async_session_maker
from app.pipeline.normalization import NormalizationPipeline
from app.utils.logging import get_logger

logger = get_logger(__name__)


@activity.defn
async def normalize_and_classify_document(document_id: str) -> Dict:
    """Normalize document, extract classification signals, and extract entities."""
    try:
        activity.logger.info(f"[Phase 2: Normalization] Starting normalization for document: {document_id}")
        activity.heartbeat("Starting normalization")
        
        async with async_session_maker() as session:
            # Fetch OCR pages
            from app.repositories.document_repository import DocumentRepository
            doc_repo = DocumentRepository(session)
            pages = await doc_repo.get_pages_by_document(UUID(document_id))
            
            if not pages:
                raise ValueError(f"No OCR pages found for document {document_id}")
            
            activity.logger.info(f"[Phase 2: Normalization] Retrieved {len(pages)} pages for normalization")
            
            pipeline = NormalizationPipeline(session)
            activity.logger.info("[Phase 2: Normalization] Starting batch normalization and section-type detection")
            
            result, classification = await pipeline.process_document(UUID(document_id), pages)
            
            await session.commit()
        
        chunk_count = len(result) if isinstance(result, list) else 0
        section_types = {}
        if isinstance(result, list):
            for chunk in result:
                section_type = chunk.get('section_type', 'UNKNOWN')
                section_types[section_type] = section_types.get(section_type, 0) + 1
        
        activity.logger.info(
            f"[Phase 2: Normalization] Normalization complete for {document_id}: "
            f"classified as {classification.get('classified_type', 'unknown') if classification else 'unknown'}"
        )
        
        return {
            "chunk_count": chunk_count,
            "normalized_count": chunk_count,
            "entity_count": 0,  # Computed later
            "classification": classification or {},
            "section_types": section_types,
        }
        
    except Exception as e:
        activity.logger.error(f"Normalization failed for {document_id}: {e}")
        raise
