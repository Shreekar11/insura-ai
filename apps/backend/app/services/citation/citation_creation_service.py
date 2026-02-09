"""Citation creation service for building citations from synthesis results.

This service creates citations from synthesized coverages and exclusions,
mapping them back to their source locations in PDF documents.

Uses CitationResolutionService for tiered coordinate resolution:
- Tier 1: Direct text match via CitationMapper
- Tier 2: Semantic chunk search via chunk embeddings
- Tier 3: Placeholder fallback
"""

from decimal import Decimal
from typing import List, Dict, Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.services.citation.citation_service import CitationService
from app.services.citation.citation_mapper import CitationMapper
from app.services.citation.citation_resolution_service import CitationResolutionService
from app.repositories.document_repository import DocumentRepository
from app.schemas.citation import (
    CitationCreate,
    CitationResponse,
    PageRange,
    SourceType,
    ExtractionMethod,
)
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


def _to_dict(item: Any) -> Dict[str, Any]:
    """Convert item to dictionary, handling Pydantic models."""
    if isinstance(item, dict):
        return item
    elif isinstance(item, BaseModel):
        return item.model_dump()
    elif hasattr(item, "__dict__"):
        return vars(item)
    else:
        return {"value": item}


class CitationCreationService:
    """Service for creating citations from synthesis results.

    Creates citation records that map effective coverages and exclusions
    back to their source locations in the original PDF documents.

    Uses CitationResolutionService for tiered bounding box resolution:
    Tier 1 (direct text match) → Tier 2 (semantic chunk search) → Tier 3 (placeholder).
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.citation_service = CitationService(session)
        self.doc_repo = DocumentRepository(session)
        self._citation_mapper: Optional[CitationMapper] = None
        self._resolution_service: Optional[CitationResolutionService] = None
        self._current_document_id: Optional[UUID] = None

    async def _ensure_resolution_service(self, document_id: UUID) -> CitationResolutionService:
        """Ensure resolution service is initialized for the document.

        Lazily loads word coordinates, creates CitationMapper, and wraps
        both in a CitationResolutionService for tiered resolution.
        """
        if self._resolution_service and self._current_document_id == document_id:
            return self._resolution_service

        mapper = None
        try:
            word_index, page_metadata = await self.doc_repo.get_word_coordinates_for_citation(
                document_id
            )

            if word_index:
                mapper = CitationMapper(word_index, page_metadata)
                LOGGER.info(
                    "[CITATION] CitationMapper initialized",
                    extra={
                        "document_id": str(document_id),
                        "pages_with_words": len(word_index),
                        "total_pages": len(page_metadata),
                    },
                )
            else:
                LOGGER.info(
                    "[CITATION] No word coordinates available",
                    extra={"document_id": str(document_id)},
                )
        except Exception as e:
            LOGGER.warning(
                f"[CITATION] Failed to initialize CitationMapper: {e}",
                extra={"document_id": str(document_id)},
            )

        self._citation_mapper = mapper
        self._resolution_service = CitationResolutionService(
            session=self.session,
            citation_mapper=mapper,
        )
        self._current_document_id = document_id
        return self._resolution_service

    async def create_citations_from_synthesis(
        self,
        document_id: UUID,
        effective_coverages: List[Dict[str, Any]],
        effective_exclusions: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Create citations for all effective coverages and exclusions.

        Args:
            document_id: UUID of the source document
            effective_coverages: List of synthesized coverage dictionaries
            effective_exclusions: List of synthesized exclusion dictionaries

        Returns:
            Dict with created citation counts and any errors
        """
        created_count = 0
        skipped_count = 0
        errors = []
        resolution_stats = {"direct_text_match": 0, "semantic_chunk_match": 0, "placeholder": 0}

        await self._ensure_resolution_service(document_id)

        LOGGER.info(
            "="*60 + "\n[CITATION] Starting citation creation from synthesis\n" + "="*60,
            extra={
                "document_id": str(document_id),
                "coverage_count": len(effective_coverages),
                "exclusion_count": len(effective_exclusions),
                "citation_mapper_available": self._citation_mapper is not None,
            },
        )

        if effective_coverages:
            sample = _to_dict(effective_coverages[0])
            LOGGER.info(
                "[CITATION] Sample coverage item structure",
                extra={
                    "sample_keys": list(sample.keys()),
                    "has_canonical_id": "canonical_id" in sample,
                    "has_page_numbers": "page_numbers" in sample,
                    "has_source_text": "source_text" in sample,
                    "has_description": "description" in sample,
                    "canonical_id": sample.get("canonical_id"),
                    "page_numbers": sample.get("page_numbers"),
                    "coverage_name": sample.get("coverage_name"),
                },
            )

        # Create citations for coverages
        for i, coverage in enumerate(effective_coverages):
            coverage_dict = _to_dict(coverage)
            coverage_name = coverage_dict.get("coverage_name", f"coverage_{i}")

            LOGGER.debug(
                f"[CITATION] Processing coverage {i+1}/{len(effective_coverages)}: {coverage_name}",
                extra={
                    "canonical_id": coverage_dict.get("canonical_id"),
                    "page_numbers": coverage_dict.get("page_numbers"),
                    "has_source_text": bool(coverage_dict.get("source_text")),
                    "has_description": bool(coverage_dict.get("description")),
                },
            )

            try:
                citation = await self._create_citation_from_item(
                    document_id=document_id,
                    item=coverage_dict,
                    source_type=SourceType.EFFECTIVE_COVERAGE,
                )
                if citation:
                    created_count += 1
                    if citation.resolution_method:
                        resolution_stats[citation.resolution_method] = (
                            resolution_stats.get(citation.resolution_method, 0) + 1
                        )
                    LOGGER.info(
                        f"[CITATION] Created citation for coverage: {coverage_name}",
                        extra={
                            "citation_id": str(citation.id),
                            "canonical_id": coverage_dict.get("canonical_id"),
                            "primary_page": citation.primary_page,
                            "resolution_method": citation.resolution_method,
                        },
                    )
                else:
                    skipped_count += 1
            except Exception as e:
                error_msg = f"Failed to create citation for coverage {coverage_dict.get('canonical_id')}: {e}"
                LOGGER.error(f"[CITATION] Exception for coverage {coverage_name}: {e}", exc_info=True)
                errors.append(error_msg)

        # Create citations for exclusions
        for i, exclusion in enumerate(effective_exclusions):
            exclusion_dict = _to_dict(exclusion)
            exclusion_name = exclusion_dict.get("exclusion_name", f"exclusion_{i}")

            LOGGER.debug(
                f"[CITATION] Processing exclusion {i+1}/{len(effective_exclusions)}: {exclusion_name}",
                extra={
                    "canonical_id": exclusion_dict.get("canonical_id"),
                    "page_numbers": exclusion_dict.get("page_numbers"),
                    "has_source_text": bool(exclusion_dict.get("source_text")),
                    "has_description": bool(exclusion_dict.get("description")),
                },
            )

            try:
                citation = await self._create_citation_from_item(
                    document_id=document_id,
                    item=exclusion_dict,
                    source_type=SourceType.EFFECTIVE_EXCLUSION,
                )
                if citation:
                    created_count += 1
                    if citation.resolution_method:
                        resolution_stats[citation.resolution_method] = (
                            resolution_stats.get(citation.resolution_method, 0) + 1
                        )
                    LOGGER.info(
                        f"[CITATION] Created citation for exclusion: {exclusion_name}",
                        extra={
                            "citation_id": str(citation.id),
                            "canonical_id": exclusion_dict.get("canonical_id"),
                            "primary_page": citation.primary_page,
                            "resolution_method": citation.resolution_method,
                        },
                    )
                else:
                    skipped_count += 1
            except Exception as e:
                error_msg = f"Failed to create citation for exclusion {exclusion_dict.get('canonical_id')}: {e}"
                LOGGER.error(f"[CITATION] Exception for exclusion {exclusion_name}: {e}", exc_info=True)
                errors.append(error_msg)

        LOGGER.info(
            "="*60 + "\n[CITATION] Citation creation completed\n" + "="*60,
            extra={
                "document_id": str(document_id),
                "created_count": created_count,
                "skipped_count": skipped_count,
                "coverage_count": len(effective_coverages),
                "exclusion_count": len(effective_exclusions),
                "error_count": len(errors),
                "resolution_stats": resolution_stats,
                "errors": errors[:5] if errors else [],
            },
        )
        
        await self.session.commit()

        return {
            "created_count": created_count,
            "skipped_count": skipped_count,
            "errors": errors,
            "resolution_stats": resolution_stats,
        }

    async def _create_citation_from_item(
        self,
        document_id: UUID,
        item: Dict[str, Any],
        source_type: SourceType,
    ) -> Optional[CitationResponse]:
        """Create a citation from a synthesized item."""
        item_name = item.get('coverage_name') or item.get('exclusion_name') or 'unknown'

        source_id = item.get("canonical_id")
        if not source_id:
            LOGGER.warning(
                f"[CITATION] SKIP - No canonical_id for: {item_name}",
                extra={"item_name": item_name, "source_type": source_type.value},
            )
            return None

        page_numbers = self._extract_page_numbers(item)
        if not page_numbers:
            LOGGER.warning(
                f"[CITATION] SKIP - No page_numbers for: {item_name} ({source_id})",
                extra={
                    "source_id": source_id,
                    "page_numbers_field": item.get("page_numbers"),
                    "page_range_field": item.get("page_range"),
                    "page_number_field": item.get("page_number"),
                },
            )
            return None

        source_text = self._extract_source_text(item)
        if not source_text:
            source_text = item.get("description", "")
            if not source_text:
                LOGGER.warning(
                    f"[CITATION] SKIP - No source_text or description for: {item_name} ({source_id})",
                )
                return None

        LOGGER.info(
            f"[CITATION] Resolving citation for: {item_name}",
            extra={
                "source_id": source_id,
                "source_type": source_type.value,
                "page_numbers": page_numbers,
                "text_length": len(source_text),
            },
        )

        # Use tiered resolution service (Tier 1 → Tier 2 → Tier 3)
        resolution = await self._resolution_service.resolve(
            source_text=source_text,
            document_id=document_id,
            expected_page=min(page_numbers),
            page_numbers=page_numbers,
        )

        primary_page = min(page_numbers) if page_numbers else 1

        page_range = None
        if len(page_numbers) > 1:
            page_range = PageRange(start=min(page_numbers), end=max(page_numbers))

        confidence = item.get("confidence")
        if confidence is not None:
            confidence = Decimal(str(confidence))

        citation_data = CitationCreate(
            document_id=document_id,
            source_type=source_type,
            source_id=source_id,
            spans=resolution.spans,
            verbatim_text=source_text[:5000],
            primary_page=primary_page,
            page_range=page_range,
            extraction_confidence=confidence,
            extraction_method=ExtractionMethod.DOCLING,
            clause_reference=item.get("clause_reference"),
            resolution_method=resolution.method,
        )

        return await self.citation_service.create_citation(citation_data)

    def _extract_page_numbers(self, item: Dict[str, Any]) -> List[int]:
        """Extract page numbers from item."""
        page_numbers = item.get("page_numbers")
        if page_numbers and isinstance(page_numbers, list):
            return [int(p) for p in page_numbers if isinstance(p, (int, float)) and p >= 1]

        page_range = item.get("page_range")
        if page_range and isinstance(page_range, dict):
            start = page_range.get("start", 1)
            end = page_range.get("end", start)
            return list(range(int(start), int(end) + 1))

        page_number = item.get("page_number")
        if page_number and isinstance(page_number, (int, float)):
            return [int(page_number)]

        return []

    def _extract_source_text(self, item: Dict[str, Any]) -> Optional[str]:
        """Extract source/verbatim text from item."""
        for field in ["source_text", "verbatim_text", "verbatim_language", "extracted_text"]:
            text = item.get(field)
            if text and isinstance(text, str) and text.strip():
                return text.strip()
        return None


__all__ = [
    "CitationCreationService",
]
