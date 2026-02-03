"""Citation creation service for building citations from synthesis results.

This service creates citations from synthesized coverages and exclusions,
mapping them back to their source locations in PDF documents.
"""

from decimal import Decimal
from typing import List, Dict, Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

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
        errors = []

        # Create citations for coverages
        for coverage in effective_coverages:
            try:
                citation = await self._create_citation_from_item(
                    document_id=document_id,
                    item=coverage,
                    source_type=SourceType.EFFECTIVE_COVERAGE,
                )
                if citation:
                    created_count += 1
            except Exception as e:
                error_msg = f"Failed to create citation for coverage {coverage.get('canonical_id')}: {e}"
                LOGGER.warning(error_msg)
                errors.append(error_msg)

        # Create citations for exclusions
        for exclusion in effective_exclusions:
            try:
                citation = await self._create_citation_from_item(
                    document_id=document_id,
                    item=exclusion,
                    source_type=SourceType.EFFECTIVE_EXCLUSION,
                )
                if citation:
                    created_count += 1
            except Exception as e:
                error_msg = f"Failed to create citation for exclusion {exclusion.get('canonical_id')}: {e}"
                LOGGER.warning(error_msg)
                errors.append(error_msg)

        LOGGER.info(
            "Citation creation completed",
            extra={
                "document_id": str(document_id),
                "created_count": created_count,
                "coverage_count": len(effective_coverages),
                "exclusion_count": len(effective_exclusions),
                "error_count": len(errors),
            }
        )

        return {
            "created_count": created_count,
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
        # Get canonical_id as source_id
        source_id = item.get("canonical_id")
        if not source_id:
            LOGGER.debug(f"Skipping item without canonical_id: {item.get('coverage_name') or item.get('exclusion_name')}")
            return None

        # Get page numbers
        page_numbers = self._extract_page_numbers(item)
        if not page_numbers:
            LOGGER.debug(f"Skipping item without page_numbers: {source_id}")
            return None

        # Get source text (verbatim text)
        source_text = self._extract_source_text(item)
        if not source_text:
            # Use description as fallback
            source_text = item.get("description", "")
            if not source_text:
                LOGGER.debug(f"Skipping item without source_text: {source_id}")
                return None

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
