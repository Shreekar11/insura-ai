"""Phase 3: Hybrid Chunking activities."""

from temporalio import activity
from typing import Dict, List, Optional
from uuid import UUID

from app.core.config import settings
from app.core.database import async_session_maker
from app.services.processed.services.chunking.hybrid_chunking_service import HybridChunkingService
from app.repositories.section_chunk_repository import SectionChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.utils.logging import get_logger
from app.temporal.core.activity_registry import ActivityRegistry

logger = get_logger(__name__)


@ActivityRegistry.register("shared", "perform_hybrid_chunking")
@activity.defn
async def perform_hybrid_chunking(
    workflow_id: str,
    document_id: str,
    page_section_map: Optional[Dict[int, str]] = None,
    target_sections: Optional[List[str]] = None,
    section_boundaries: Optional[List[Dict]] = None,
) -> Dict:
    """Perform hybrid chunking on document pages."""
    try:
        has_section_map = page_section_map is not None
        has_boundaries = section_boundaries is not None
        
        activity.logger.info(
            f"[Phase 3: Hybrid Chunking] Starting hybrid chunking for document: {document_id}",
            extra={
                "workflow_id": workflow_id,
                "document_id": document_id,
                "has_section_map": has_section_map,
                "has_boundaries": has_boundaries,
                "section_map_size": len(page_section_map) if page_section_map else 0,
            }
        )
        activity.heartbeat("Starting hybrid chunking")
        
        # Convert section boundary dicts to SectionBoundary objects if provided
        boundaries = None
        if section_boundaries:
            from app.models.page_analysis_models import SectionBoundary, PageType, SemanticRole
            boundaries = []

            # Log raw boundary data for debugging
            boundaries_with_role = sum(1 for b in section_boundaries if b.get('semantic_role'))
            activity.logger.info(
                f"[Phase 3: Chunking] Processing {len(section_boundaries)} boundaries, "
                f"{boundaries_with_role} have semantic_role set",
                extra={
                    "total_boundaries": len(section_boundaries),
                    "boundaries_with_semantic_role": boundaries_with_role,
                }
            )

            for b in section_boundaries:
                # PageType is an enum, we need to convert from string
                st_value = b.get('section_type')
                try:
                    section_type = PageType(st_value)
                except ValueError:
                    section_type = PageType.UNKNOWN
                
                # Handle enum conversion for effective_section_type
                eff_st_value = b.get('effective_section_type')
                effective_section_type = None
                if eff_st_value:
                    try:
                        effective_section_type = PageType(eff_st_value)
                    except ValueError:
                        effective_section_type = None

                # Handle SemanticRole enum
                role_val = b.get('semantic_role')
                semantic_role = None
                if role_val:
                    try:
                        semantic_role = SemanticRole(role_val)
                    except ValueError:
                        semantic_role = None
                
                boundaries.append(SectionBoundary(
                    section_type=section_type,
                    start_page=b.get('start_page'),
                    end_page=b.get('end_page'),
                    start_line=b.get('start_line'),
                    end_line=b.get('end_line'),
                    confidence=b.get('confidence', 1.0),
                    page_count=b.get('page_count', 1),
                    anchor_text=b.get('anchor_text'),
                    semantic_role=semantic_role,
                    effective_section_type=effective_section_type,
                    coverage_effects=b.get('coverage_effects', []),
                    exclusion_effects=b.get('exclusion_effects', []),
                    sub_section_type=b.get('sub_section_type')
                ))

            # Log endorsement boundaries with their semantic info for debugging
            endorsement_boundaries = [bnd for bnd in boundaries if bnd.section_type == PageType.ENDORSEMENT]
            if endorsement_boundaries:
                activity.logger.info(
                    f"[Phase 3: Chunking] Found {len(endorsement_boundaries)} endorsement boundaries",
                    extra={
                        "endorsement_boundaries": [
                            {
                                "pages": f"{bnd.start_page}-{bnd.end_page}",
                                "semantic_role": bnd.semantic_role.value if bnd.semantic_role else None,
                                "effective_section_type": bnd.effective_section_type.value if bnd.effective_section_type else None,
                            }
                            for bnd in endorsement_boundaries
                        ]
                    }
                )

        async with async_session_maker() as session:
            # Fetch OCR pages
            doc_repo = DocumentRepository(session)
            pages = await doc_repo.get_pages_by_document(document_id=UUID(document_id))
            
            if not pages:
                raise ValueError(f"No OCR pages found for document {document_id}")
            
            # Apply section filtering if target_sections is provided
            if target_sections:
                activity.logger.info(f"[Phase 3: Hybrid Chunking] Filtering for sections: {target_sections}")
                normalized_targets = [s.lower().replace(" ", "_").strip() for s in target_sections]

                if page_section_map:
                    # Filter section map
                    filtered_map = {
                        str(p): s for p, s in page_section_map.items()
                        if any(st.lower().replace(" ", "_").strip() in normalized_targets
                               for st in s.split(","))
                    }
                    target_page_nums = {int(p) for p in filtered_map.keys()}

                    # Filter pages
                    original_count = len(pages)
                    filtered_pages = [p for p in pages if p.page_number in target_page_nums]

                    # Check if filtering would result in empty pages
                    if not filtered_pages:
                        # Skip filtering - process all pages with a warning
                        activity.logger.warning(
                            f"[Phase 3: Hybrid Chunking] Filtering would result in 0 pages. "
                            f"Skipping filter and processing all {original_count} pages. "
                            f"Document may not contain expected section types: {target_sections}. "
                            f"Available section types in page_section_map: {set(page_section_map.values())}"
                        )
                        # Don't update pages or page_section_map - use original values
                    else:
                        # Apply filtering
                        pages = filtered_pages
                        page_section_map = filtered_map

                        # Also filter boundaries if present
                        if boundaries:
                            boundaries = [
                                b for b in boundaries
                                if b.section_type.value.lower().replace(" ", "_").strip() in normalized_targets
                            ]

                        activity.logger.info(
                            f"[Phase 3: Hybrid Chunking] Filtered pages: {original_count} -> {len(pages)} "
                            f"based on target sections"
                        )

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
            chunking_service = HybridChunkingService(
                max_tokens=settings.chunk_max_tokens,
                overlap_tokens=settings.chunk_overlap_tokens,
                min_tokens_per_chunk=settings.chunk_min_tokens,
                max_tokens_per_super_chunk=settings.max_tokens_per_super_chunk,
            )
            
            section_source = "manifest" if (has_section_map or has_boundaries) else "auto-detect"
            
            # chunk_pages now handles both chunking AND super-chunk building
            chunking_result = chunking_service.chunk_pages(
                pages=pages,
                document_id=UUID(document_id),
                page_section_map=page_section_map,
                section_boundaries=boundaries,
            )
            
            activity.heartbeat(f"Created {len(chunking_result.chunks)} chunks")
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
            exc_info=True
        )
        raise
