"""Phase 3: Hybrid Chunking activities.

These activities handle section-aware hybrid chunking using Docling.
Now accepts page_section_map from manifest to ensure consistent section
assignment with page analysis.
"""

from temporalio import activity
from typing import Dict, List, Optional
from uuid import UUID

from app.core.config import settings
from app.core.database import async_session_maker
from app.services.processed.services.chunking.hybrid_chunking_service import HybridChunkingService
from app.repositories.section_chunk_repository import SectionChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.utils.logging import get_logger

logger = get_logger(__name__)


@activity.defn
async def perform_hybrid_chunking(
    workflow_id: str,
    document_id: str,
    page_section_map: Optional[Dict[int, str]] = None,
) -> Dict:
    """Perform hybrid chunking on document pages.
    
    This activity:
    1. Retrieves OCR-extracted pages from the database
    2. Uses page_section_map from manifest for section assignment (if provided)
    3. Performs hybrid chunking using Docling
    4. Creates section super-chunks
    5. Persists chunks and super-chunks to database
    
    Args:
        document_id: UUID of the document to chunk
        page_section_map: Optional mapping of page numbers to section types
            from page analysis manifest. If provided, this ensures
            consistent section assignment without re-detection.
        
    Returns:
        Dictionary with chunking statistics
    """
    try:
        has_section_map = page_section_map is not None
        
        activity.logger.info(
            f"[Phase 3: Hybrid Chunking] Starting hybrid chunking for document: {document_id}",
            extra={
                "workflow_id": workflow_id,
                "document_id": document_id,
                "has_section_map": has_section_map,
                "section_map_size": len(page_section_map) if page_section_map else 0,
            }
        )
        activity.heartbeat("Starting hybrid chunking")
        
        async with async_session_maker() as session:
            # Fetch OCR pages
            doc_repo = DocumentRepository(session)
            pages = await doc_repo.get_pages_by_document(document_id=UUID(document_id))
            
            if not pages:
                raise ValueError(f"No OCR pages found for document {document_id}")
            
            activity.logger.info(
                f"[Phase 3: Hybrid Chunking] Retrieved {len(pages)} pages for chunking",
                extra={
                    "workflow_id": workflow_id,
                    "document_id": document_id,
                    "page_count": len(pages),
                    "pages_with_metadata": sum(1 for p in pages if p.metadata),
                }
            )
            activity.heartbeat(f"Retrieved {len(pages)} pages")
            
            # Perform hybrid chunking with section map from manifest
            # Uses config-based token limits for super-chunk splitting
            chunking_service = HybridChunkingService(
                max_tokens=settings.chunk_max_tokens,
                overlap_tokens=settings.chunk_overlap_tokens,
                max_tokens_per_super_chunk=settings.max_tokens_per_super_chunk,
            )
            
            section_source = "manifest" if has_section_map else "auto-detect"
            activity.logger.info(
                f"[Phase 3: Hybrid Chunking] Performing hybrid chunking (section source: {section_source})",
                extra={
                    "max_tokens_per_super_chunk": settings.max_tokens_per_super_chunk,
                }
            )
            
            # chunk_pages now handles both chunking AND super-chunk building
            # with proper token-based splitting to respect LLM limits
            chunking_result = chunking_service.chunk_pages(
                pages=pages,
                document_id=UUID(document_id),
                page_section_map=page_section_map,
            )
            
            activity.heartbeat(f"Created {len(chunking_result.chunks)} chunks")
            
            # Super-chunks are already built by chunk_pages with token limits
            super_chunks = chunking_result.super_chunks
            
            activity.heartbeat(f"Created {len(super_chunks)} super-chunks")
            
            # Persist to database
            activity.logger.info("[Phase 3: Hybrid Chunking] Persisting chunks to database...")
            chunk_repo = SectionChunkRepository(session)
            await chunk_repo.save_chunking_result(chunking_result, document_id)
            
            await session.commit()
            
            activity.logger.info(
                f"[Phase 3: Hybrid Chunking] Chunking complete for {document_id}: "
                f"{len(chunking_result.chunks)} chunks, "
                f"{len(super_chunks)} super-chunks, "
                f"{len(chunking_result.section_map)} sections detected",
                extra={
                    "document_id": document_id,
                    "chunk_count": len(chunking_result.chunks),
                    "super_chunk_count": len(super_chunks),
                    "sections": list(chunking_result.section_map.keys()),
                    "section_source": section_source,
                }
            )
            
            # Prepare statistics
            return {
                "chunk_count": len(chunking_result.chunks),
                "super_chunk_count": len(super_chunks),
                "sections_detected": list(chunking_result.section_map.keys()),
                "section_stats": chunking_result.section_map,
                "total_tokens": chunking_result.total_tokens,
                "avg_tokens_per_chunk": chunking_result.statistics.get("avg_tokens_per_chunk", 0),
                "section_source": section_source,
            }
            
    except Exception as e:
        activity.logger.error(
            f"Hybrid chunking failed for {document_id}: {e}",
            extra={
                "document_id": document_id,
                "has_section_map": page_section_map is not None,
                "error_type": type(e).__name__,
            },
            exc_info=True
        )
        raise

