"""Service for extracting word-level coordinates from PDF documents.

Uses pdfplumber to capture precise bounding boxes for text elements,
enabling citation source mapping for extracted items.

This service is used during the extraction pipeline to persist
word-level coordinates that can later be used to map extracted
text (coverages, exclusions, etc.) back to their source locations.
"""

from dataclasses import dataclass, field
from io import BytesIO
from typing import Dict, List, Optional, Tuple

from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


@dataclass
class WordCoordinate:
    """Word with its bounding box coordinates.

    Coordinates are in PDF coordinate system:
    - Origin at bottom-left of page
    - Y-axis increases upward
    - Units in PDF points (1 point = 1/72 inch)
    """

    text: str
    page_number: int  # 1-indexed
    x0: float  # Left coordinate
    y0: float  # Bottom coordinate (PDF coords)
    x1: float  # Right coordinate
    y1: float  # Top coordinate (PDF coords)
    fontname: Optional[str] = None
    size: Optional[float] = None


@dataclass
class PageMetadata:
    """Page dimension metadata for coordinate transformation."""

    page_number: int  # 1-indexed
    width: float  # Width in PDF points
    height: float  # Height in PDF points
    rotation: int = 0  # Rotation in degrees


@dataclass
class CoordinateExtractionResult:
    """Result of coordinate extraction from a PDF."""

    words: List[WordCoordinate]
    pages: List[PageMetadata]
    total_words: int = field(init=False)
    total_pages: int = field(init=False)

    def __post_init__(self):
        self.total_words = len(self.words)
        self.total_pages = len(self.pages)


class CoordinateExtractionService:
    """Service for extracting word-level coordinates from PDFs.

    This service uses pdfplumber to extract precise bounding boxes
    for every word in a PDF document. The coordinates can then be
    used by the CitationMapper to map extracted text back to its
    source location.

    Example usage:
        service = CoordinateExtractionService()
        result = await service.extract_word_coordinates(pdf_bytes)
        word_index = service.build_text_index(result.words)
    """

    def __init__(self):
        """Initialize the coordinate extraction service."""
        self._pdfplumber = None

    @property
    def pdfplumber(self):
        """Lazy-load pdfplumber to avoid import overhead."""
        if self._pdfplumber is None:
            import pdfplumber
            self._pdfplumber = pdfplumber
        return self._pdfplumber

    async def extract_word_coordinates(
        self,
        pdf_bytes: bytes,
        pages_to_extract: Optional[List[int]] = None,
    ) -> CoordinateExtractionResult:
        """Extract all words with bounding boxes from PDF.

        Args:
            pdf_bytes: PDF file content as bytes
            pages_to_extract: Optional list of 1-indexed page numbers to extract.
                            If None, extracts all pages.

        Returns:
            CoordinateExtractionResult containing words and page metadata
        """
        words: List[WordCoordinate] = []
        pages: List[PageMetadata] = []

        try:
            with self.pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
                total_pages = len(pdf.pages)
                LOGGER.info(
                    f"Starting coordinate extraction for {total_pages} pages",
                    extra={"total_pages": total_pages}
                )

                for page_num, page in enumerate(pdf.pages, start=1):
                    # Skip pages not in the extraction list
                    if pages_to_extract and page_num not in pages_to_extract:
                        continue

                    # Store page dimensions
                    pages.append(PageMetadata(
                        page_number=page_num,
                        width=float(page.width),
                        height=float(page.height),
                        rotation=page.rotation or 0
                    ))

                    # Extract words with coordinates
                    page_words = page.extract_words(
                        keep_blank_chars=True,
                        x_tolerance=3,
                        y_tolerance=3,
                        extra_attrs=["fontname", "size"]
                    )

                    for word in page_words:
                        # Convert pdfplumber coordinates to PDF coordinates
                        # pdfplumber uses top-left origin, we convert to bottom-left
                        words.append(WordCoordinate(
                            text=word["text"],
                            page_number=page_num,
                            x0=word["x0"],
                            # Convert from top-origin to bottom-origin
                            y0=float(page.height) - word["bottom"],
                            x1=word["x1"],
                            y1=float(page.height) - word["top"],
                            fontname=word.get("fontname"),
                            size=word.get("size")
                        ))

            LOGGER.info(
                f"Coordinate extraction completed",
                extra={
                    "total_words": len(words),
                    "total_pages": len(pages)
                }
            )

            return CoordinateExtractionResult(words=words, pages=pages)

        except Exception as e:
            LOGGER.error(
                f"Coordinate extraction failed: {e}",
                extra={"error_type": type(e).__name__},
                exc_info=True
            )
            raise

    def build_text_index(
        self,
        words: List[WordCoordinate]
    ) -> Dict[int, List[WordCoordinate]]:
        """Build page-indexed word lookup for fast searching.

        Args:
            words: List of WordCoordinate objects

        Returns:
            Dictionary mapping page numbers to lists of words on that page
        """
        index: Dict[int, List[WordCoordinate]] = {}
        for word in words:
            if word.page_number not in index:
                index[word.page_number] = []
            index[word.page_number].append(word)

        # Sort words on each page by position (top-to-bottom, left-to-right)
        for page_num in index:
            index[page_num].sort(key=lambda w: (-w.y1, w.x0))

        return index

    def get_page_dimensions(
        self,
        pages: List[PageMetadata],
        page_number: int
    ) -> Optional[PageMetadata]:
        """Get dimensions for a specific page.

        Args:
            pages: List of PageMetadata objects
            page_number: 1-indexed page number

        Returns:
            PageMetadata for the requested page, or None if not found
        """
        for page in pages:
            if page.page_number == page_number:
                return page
        return None

    def extract_words_in_region(
        self,
        words: List[WordCoordinate],
        page_number: int,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        tolerance: float = 5.0
    ) -> List[WordCoordinate]:
        """Extract words within a specific region on a page.

        Args:
            words: List of all WordCoordinate objects
            page_number: Page number to search
            x0, y0, x1, y1: Bounding box coordinates (PDF coordinate system)
            tolerance: Padding around the region in points

        Returns:
            List of words within the specified region
        """
        region_words = []
        for word in words:
            if word.page_number != page_number:
                continue

            # Check if word overlaps with region (with tolerance)
            if (word.x0 >= x0 - tolerance and
                word.x1 <= x1 + tolerance and
                word.y0 >= y0 - tolerance and
                word.y1 <= y1 + tolerance):
                region_words.append(word)

        # Sort by position (top-to-bottom, left-to-right)
        region_words.sort(key=lambda w: (-w.y1, w.x0))
        return region_words


# Module-level singleton for reuse
_coordinate_service_instance: Optional[CoordinateExtractionService] = None


def get_coordinate_extraction_service() -> CoordinateExtractionService:
    """Get or create the coordinate extraction service singleton.

    Returns:
        CoordinateExtractionService instance
    """
    global _coordinate_service_instance
    if _coordinate_service_instance is None:
        _coordinate_service_instance = CoordinateExtractionService()
    return _coordinate_service_instance


__all__ = [
    "WordCoordinate",
    "PageMetadata",
    "CoordinateExtractionResult",
    "CoordinateExtractionService",
    "get_coordinate_extraction_service",
]
