"""Citation creation service for building citations from synthesis results.

This service creates citations from synthesized coverages and exclusions,
mapping them back to their source locations in PDF documents.
"""

from decimal import Decimal
from typing import List, Dict, Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.services.citation.citation_service import CitationService
from app.schemas.citation import (
    BoundingBox,
    CitationCreate,
    CitationResponse,
    CitationSpan,
    PageRange,
    SourceType,
    ExtractionMethod,
)
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


def _to_dict(item: Any) -> Dict[str, Any]:
    """Convert item to dictionary, handling Pydantic models.

    Args:
        item: A dict, Pydantic model, or other object

    Returns:
        Dictionary representation of the item
    """
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
    """

    def __init__(self, session: AsyncSession):
        """Initialize the citation creation service.

        Args:
            session: SQLAlchemy async session
        """
        self.session = session
        self.citation_service = CitationService(session)

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

        LOGGER.info(
            "="*60 + "\n[CITATION] Starting citation creation from synthesis\n" + "="*60,
            extra={
                "document_id": str(document_id),
                "coverage_count": len(effective_coverages),
                "exclusion_count": len(effective_exclusions),
            }
        )

        # Log sample of first coverage for debugging
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
                }
            )

        # Create citations for coverages
        for i, coverage in enumerate(effective_coverages):
            # Convert to dict if it's a Pydantic model
            coverage_dict = _to_dict(coverage)
            coverage_name = coverage_dict.get("coverage_name", f"coverage_{i}")

            LOGGER.debug(
                f"[CITATION] Processing coverage {i+1}/{len(effective_coverages)}: {coverage_name}",
                extra={
                    "canonical_id": coverage_dict.get("canonical_id"),
                    "page_numbers": coverage_dict.get("page_numbers"),
                    "has_source_text": bool(coverage_dict.get("source_text")),
                    "has_description": bool(coverage_dict.get("description")),
                }
            )

            try:
                citation = await self._create_citation_from_item(
                    document_id=document_id,
                    item=coverage_dict,
                    source_type=SourceType.EFFECTIVE_COVERAGE,
                )
                if citation:
                    created_count += 1
                    LOGGER.info(
                        f"[CITATION] ✓ Created citation for coverage: {coverage_name}",
                        extra={
                            "citation_id": str(citation.id),
                            "canonical_id": coverage_dict.get("canonical_id"),
                            "primary_page": citation.primary_page,
                        }
                    )
                else:
                    skipped_count += 1
                    LOGGER.warning(
                        f"[CITATION] ✗ Skipped coverage (returned None): {coverage_name}",
                        extra={"canonical_id": coverage_dict.get("canonical_id")}
                    )
            except Exception as e:
                error_msg = f"Failed to create citation for coverage {coverage_dict.get('canonical_id')}: {e}"
                LOGGER.error(f"[CITATION] ✗ Exception for coverage {coverage_name}: {e}", exc_info=True)
                errors.append(error_msg)

        # Create citations for exclusions
        for i, exclusion in enumerate(effective_exclusions):
            # Convert to dict if it's a Pydantic model
            exclusion_dict = _to_dict(exclusion)
            exclusion_name = exclusion_dict.get("exclusion_name", f"exclusion_{i}")

            LOGGER.debug(
                f"[CITATION] Processing exclusion {i+1}/{len(effective_exclusions)}: {exclusion_name}",
                extra={
                    "canonical_id": exclusion_dict.get("canonical_id"),
                    "page_numbers": exclusion_dict.get("page_numbers"),
                    "has_source_text": bool(exclusion_dict.get("source_text")),
                    "has_description": bool(exclusion_dict.get("description")),
                }
            )

            try:
                citation = await self._create_citation_from_item(
                    document_id=document_id,
                    item=exclusion_dict,
                    source_type=SourceType.EFFECTIVE_EXCLUSION,
                )
                if citation:
                    created_count += 1
                    LOGGER.info(
                        f"[CITATION] ✓ Created citation for exclusion: {exclusion_name}",
                        extra={
                            "citation_id": str(citation.id),
                            "canonical_id": exclusion_dict.get("canonical_id"),
                            "primary_page": citation.primary_page,
                        }
                    )
                else:
                    skipped_count += 1
                    LOGGER.warning(
                        f"[CITATION] ✗ Skipped exclusion (returned None): {exclusion_name}",
                        extra={"canonical_id": exclusion_dict.get("canonical_id")}
                    )
            except Exception as e:
                error_msg = f"Failed to create citation for exclusion {exclusion_dict.get('canonical_id')}: {e}"
                LOGGER.error(f"[CITATION] ✗ Exception for exclusion {exclusion_name}: {e}", exc_info=True)
                errors.append(error_msg)

        LOGGER.info(
            "="*60 + f"\n[CITATION] Citation creation completed\n" + "="*60,
            extra={
                "document_id": str(document_id),
                "created_count": created_count,
                "skipped_count": skipped_count,
                "coverage_count": len(effective_coverages),
                "exclusion_count": len(effective_exclusions),
                "error_count": len(errors),
                "errors": errors[:5] if errors else [],  # First 5 errors
            }
        )

        return {
            "created_count": created_count,
            "skipped_count": skipped_count,
            "errors": errors,
        }

    async def _create_citation_from_item(
        self,
        document_id: UUID,
        item: Dict[str, Any],
        source_type: SourceType,
    ) -> Optional[CitationResponse]:
        """Create a citation from a synthesized item.

        Args:
            document_id: UUID of the source document
            item: Synthesized coverage or exclusion dictionary
            source_type: Type of item (coverage or exclusion)

        Returns:
            CitationResponse if created, None if skipped
        """
        item_name = item.get('coverage_name') or item.get('exclusion_name') or 'unknown'

        # Get canonical_id as source_id
        source_id = item.get("canonical_id")
        if not source_id:
            LOGGER.warning(
                f"[CITATION] SKIP - No canonical_id for: {item_name}",
                extra={
                    "item_name": item_name,
                    "available_keys": list(item.keys()),
                    "source_type": source_type.value,
                }
            )
            return None

        # Get page numbers
        page_numbers = self._extract_page_numbers(item)
        if not page_numbers:
            LOGGER.warning(
                f"[CITATION] SKIP - No page_numbers for: {item_name} ({source_id})",
                extra={
                    "source_id": source_id,
                    "available_keys": list(item.keys()),
                    "page_numbers_field": item.get("page_numbers"),
                    "page_range_field": item.get("page_range"),
                    "page_number_field": item.get("page_number"),
                }
            )
            return None

        # Get source text (verbatim text)
        source_text = self._extract_source_text(item)
        text_source_field = None
        if not source_text:
            # Use description as fallback
            source_text = item.get("description", "")
            if not source_text:
                LOGGER.warning(
                    f"[CITATION] SKIP - No source_text or description for: {item_name} ({source_id})",
                    extra={
                        "source_id": source_id,
                        "checked_fields": ["source_text", "verbatim_text", "verbatim_language", "extracted_text", "description"],
                    }
                )
                return None
            text_source_field = "description"
        else:
            # Determine which field had the text
            for field in ["source_text", "verbatim_text", "verbatim_language", "extracted_text"]:
                if item.get(field):
                    text_source_field = field
                    break

        LOGGER.info(
            f"[CITATION] Building citation for: {item_name}",
            extra={
                "source_id": source_id,
                "source_type": source_type.value,
                "page_numbers": page_numbers,
                "text_source_field": text_source_field,
                "text_length": len(source_text) if source_text else 0,
                "text_preview": source_text[:100] + "..." if source_text and len(source_text) > 100 else source_text,
            }
        )

        # Build citation spans
        # For now, create spans without bounding boxes (will be populated later)
        # This allows citations to be created even without coordinate data
        spans = self._build_citation_spans(page_numbers, source_text)

        # Get primary page (first page)
        primary_page = min(page_numbers) if page_numbers else 1

        # Build page range if multiple pages
        page_range = None
        if len(page_numbers) > 1:
            page_range = PageRange(
                start=min(page_numbers),
                end=max(page_numbers)
            )

        # Get confidence
        confidence = item.get("confidence")
        if confidence is not None:
            confidence = Decimal(str(confidence))

        # Get clause reference
        clause_reference = item.get("clause_reference")

        # Create citation
        citation_data = CitationCreate(
            document_id=document_id,
            source_type=source_type,
            source_id=source_id,
            spans=spans,
            verbatim_text=source_text[:5000],  # Limit to 5000 chars
            primary_page=primary_page,
            page_range=page_range,
            extraction_confidence=confidence,
            extraction_method=ExtractionMethod.DOCLING,
            clause_reference=clause_reference,
        )

        LOGGER.debug(
            f"[CITATION] Calling citation_service.create_citation",
            extra={
                "document_id": str(document_id),
                "source_id": source_id,
                "source_type": source_type.value,
                "primary_page": primary_page,
                "span_count": len(spans),
            }
        )

        return await self.citation_service.create_citation(citation_data)

    def _extract_page_numbers(self, item: Dict[str, Any]) -> List[int]:
        """Extract page numbers from item.

        Args:
            item: Synthesized item dictionary

        Returns:
            List of page numbers (1-indexed)
        """
        # Try different field names
        page_numbers = item.get("page_numbers")
        if page_numbers and isinstance(page_numbers, list):
            # Filter out non-integers and ensure 1-indexed
            return [int(p) for p in page_numbers if isinstance(p, (int, float)) and p >= 1]

        # Try page_range
        page_range = item.get("page_range")
        if page_range and isinstance(page_range, dict):
            start = page_range.get("start", 1)
            end = page_range.get("end", start)
            return list(range(int(start), int(end) + 1))

        # Try single page_number
        page_number = item.get("page_number")
        if page_number and isinstance(page_number, (int, float)):
            return [int(page_number)]

        return []

    def _extract_source_text(self, item: Dict[str, Any]) -> Optional[str]:
        """Extract source/verbatim text from item.

        Args:
            item: Synthesized item dictionary

        Returns:
            Source text if found
        """
        # Try different field names in priority order
        field_names = [
            "source_text",
            "verbatim_text",
            "verbatim_language",
            "extracted_text",
        ]

        for field in field_names:
            text = item.get(field)
            if text and isinstance(text, str) and text.strip():
                return text.strip()

        return None

    def _build_citation_spans(
        self,
        page_numbers: List[int],
        source_text: str,
    ) -> List[CitationSpan]:
        """Build citation spans from page numbers and source text.

        Creates placeholder spans without bounding boxes.
        Bounding boxes can be populated later via citation mapper.

        Args:
            page_numbers: List of page numbers
            source_text: Source text content

        Returns:
            List of CitationSpan objects
        """
        spans = []

        # Group text by page (for simplicity, put all text on first page)
        # More sophisticated logic would split text across pages
        primary_page = min(page_numbers) if page_numbers else 1

        # Create a placeholder bounding box
        # These coordinates are placeholders - actual coordinates should be
        # populated by the citation mapper using word coordinates
        placeholder_box = BoundingBox(
            x0=0.0,
            y0=0.0,
            x1=612.0,  # Standard US Letter width in points
            y1=792.0,  # Standard US Letter height in points
        )

        spans.append(
            CitationSpan(
                page_number=primary_page,
                bounding_boxes=[placeholder_box],
                text_content=source_text[:1000],  # Limit span text
            )
        )

        # If multiple pages, create additional spans for other pages
        for page_num in page_numbers[1:]:
            spans.append(
                CitationSpan(
                    page_number=page_num,
                    bounding_boxes=[placeholder_box],
                    text_content="[continued]",
                )
            )

        return spans


__all__ = [
    "CitationCreationService",
]
