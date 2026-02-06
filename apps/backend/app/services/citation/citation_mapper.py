"""Service for mapping extracted text back to PDF coordinates.

Implements text-to-coordinate mapping using fuzzy matching
to handle OCR variations and text normalization differences.
"""

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple

from app.schemas.citation import BoundingBox, CitationSpan, TextMatch
from app.services.processed.services.ocr.coordinate_extraction_service import (
    WordCoordinate,
    PageMetadata,
)
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


@dataclass
class MatchConfig:
    """Configuration for text matching."""

    fuzzy_threshold: float = 0.85
    y_tolerance: float = 5.0  # Points for line grouping
    context_words: int = 3  # Words of context for disambiguation
    anchor_size: int = 15  # Words to use as anchor for long text matching
    word_similarity_threshold: float = 0.8  # Per-word fuzzy match threshold


class CitationMapper:
    """Maps extracted text to PDF coordinates.

    This service takes a word index (from CoordinateExtractionService)
    and can find the location of any text string in the document.

    Example usage:
        mapper = CitationMapper(word_index, page_metadata)
        match = mapper.find_text_location("Liability Coverage - We will pay...")
        if match:
            print(f"Found on page {match.page_number} with {len(match.spans)} spans")
    """

    def __init__(
        self,
        word_index: Dict[int, List[WordCoordinate]],
        page_metadata: List[PageMetadata],
        config: Optional[MatchConfig] = None
    ):
        """Initialize the citation mapper.

        Args:
            word_index: Dictionary mapping page numbers to words on that page
            page_metadata: List of page dimension metadata
            config: Optional matching configuration
        """
        self.word_index = word_index
        self.page_metadata = {p.page_number: p for p in page_metadata}
        self.config = config or MatchConfig()

    def find_text_location(
        self,
        search_text: str,
        expected_page: Optional[int] = None,
        fuzzy_threshold: Optional[float] = None
    ) -> Optional[TextMatch]:
        """Find the location of text in the document.

        Args:
            search_text: Text to find
            expected_page: Hint for starting page (optimization)
            fuzzy_threshold: Minimum similarity for fuzzy match (default from config)

        Returns:
            TextMatch with coordinates or None if not found
        """
        threshold = fuzzy_threshold or self.config.fuzzy_threshold

        # Normalize search text
        normalized_search = self._normalize_text(search_text)
        search_words = normalized_search.split()

        if not search_words:
            LOGGER.warning("Empty search text provided")
            return None

        # Determine search pages (start with expected, then expand)
        search_order = self._get_search_order(expected_page)

        for page_num in search_order:
            if page_num not in self.word_index:
                continue

            page_words = self.word_index[page_num]
            span = self._find_sequence_in_page(
                search_words,
                page_words,
                threshold
            )

            if span:
                return TextMatch(
                    matched_text=search_text,
                    spans=[span],
                    confidence=0.9,  # TODO: Calculate actual confidence
                    page_number=page_num
                )

        LOGGER.debug(
            f"Text not found in document",
            extra={"search_text_length": len(search_text)}
        )
        return None

    def find_all_occurrences(
        self,
        search_text: str,
        fuzzy_threshold: Optional[float] = None
    ) -> List[TextMatch]:
        """Find all occurrences of text in the document.

        Args:
            search_text: Text to find
            fuzzy_threshold: Minimum similarity for fuzzy match

        Returns:
            List of TextMatch objects for all occurrences
        """
        threshold = fuzzy_threshold or self.config.fuzzy_threshold
        normalized_search = self._normalize_text(search_text)
        search_words = normalized_search.split()

        if not search_words:
            return []

        matches = []
        for page_num in sorted(self.word_index.keys()):
            page_words = self.word_index[page_num]
            span = self._find_sequence_in_page(
                search_words,
                page_words,
                threshold
            )

            if span:
                matches.append(TextMatch(
                    matched_text=search_text,
                    spans=[span],
                    confidence=0.9,
                    page_number=page_num
                ))

        return matches

    def _find_sequence_in_page(
        self,
        search_words: List[str],
        page_words: List[WordCoordinate],
        threshold: float
    ) -> Optional[CitationSpan]:
        """Find word sequence in page words.

        Uses anchor-based matching for long texts (> anchor_size words)
        and full sliding window for short texts.
        """
        if not search_words or not page_words:
            return None

        page_texts = [self._normalize_text(w.text) for w in page_words]
        anchor_size = self.config.anchor_size

        # For short texts, use full sliding window (original approach)
        if len(search_words) <= anchor_size:
            for i in range(len(page_words) - len(search_words) + 1):
                window = page_texts[i:i + len(search_words)]
                similarity = self._sequence_similarity(search_words, window)
                if similarity >= threshold:
                    matched_words = page_words[i:i + len(search_words)]
                    return self._words_to_span(matched_words)
            return None

        # For long texts, use anchor-based matching:
        # 1. Find start position using first N words as anchor
        # 2. Extend to cover the full search length
        anchor_words = search_words[:anchor_size]

        for i in range(len(page_texts) - anchor_size + 1):
            anchor_window = page_texts[i:i + anchor_size]
            anchor_sim = self._sequence_similarity(anchor_words, anchor_window)

            if anchor_sim >= threshold:
                # Anchor matched — take the full span from this start position
                end_idx = min(i + len(search_words), len(page_words))
                matched_words = page_words[i:end_idx]
                return self._words_to_span(matched_words)

        return None

    def _words_to_span(self, words: List[WordCoordinate]) -> CitationSpan:
        """Convert matched words to a CitationSpan."""
        if not words:
            return None

        # Group words into lines (based on y-coordinate proximity)
        lines = self._group_into_lines(words)

        bboxes = []
        for line_words in lines:
            # Merge words in same line into single bbox
            bbox = BoundingBox(
                x0=min(w.x0 for w in line_words),
                y0=min(w.y0 for w in line_words),
                x1=max(w.x1 for w in line_words),
                y1=max(w.y1 for w in line_words),
            )
            bboxes.append(bbox)

        return CitationSpan(
            page_number=words[0].page_number,
            bounding_boxes=bboxes,
            text_content=" ".join(w.text for w in words)
        )

    def _normalize_text(self, text: str) -> str:
        """Normalize text for matching."""
        # Remove extra whitespace, lowercase
        text = re.sub(r'\s+', ' ', text.strip().lower())
        # Remove common OCR artifacts but keep basic punctuation
        text = re.sub(r'[^\w\s\-\.,;:\'"()]', '', text)
        return text

    def _sequence_similarity(
        self,
        seq1: List[str],
        seq2: List[str]
    ) -> float:
        """Calculate similarity between word sequences using fuzzy per-word matching."""
        if len(seq1) != len(seq2):
            return 0.0

        word_thresh = self.config.word_similarity_threshold
        matches = 0
        for w1, w2 in zip(seq1, seq2):
            if w1 == w2:
                matches += 1
            elif self._word_similarity(w1, w2) >= word_thresh:
                matches += 1
        return matches / len(seq1)

    @staticmethod
    def _word_similarity(w1: str, w2: str) -> float:
        """Character-level similarity between two words."""
        if not w1 or not w2:
            return 0.0
        return SequenceMatcher(None, w1, w2).ratio()

    def _group_into_lines(
        self,
        words: List[WordCoordinate],
    ) -> List[List[WordCoordinate]]:
        """Group words into lines based on y-coordinate."""
        if not words:
            return []

        y_tolerance = self.config.y_tolerance

        # Sort by y (descending - top first in PDF coords) then x
        sorted_words = sorted(words, key=lambda w: (-w.y1, w.x0))

        lines = []
        current_line = [sorted_words[0]]
        current_y = sorted_words[0].y1

        for word in sorted_words[1:]:
            if abs(word.y1 - current_y) <= y_tolerance:
                current_line.append(word)
            else:
                lines.append(sorted(current_line, key=lambda w: w.x0))
                current_line = [word]
                current_y = word.y1

        if current_line:
            lines.append(sorted(current_line, key=lambda w: w.x0))

        return lines

    def _get_search_order(self, expected_page: Optional[int]) -> List[int]:
        """Get page search order, prioritizing expected page."""
        all_pages = sorted(self.word_index.keys())

        if expected_page and expected_page in all_pages:
            # Start with expected, then nearby pages
            idx = all_pages.index(expected_page)
            order = [expected_page]
            for offset in range(1, len(all_pages)):
                if idx + offset < len(all_pages):
                    order.append(all_pages[idx + offset])
                if idx - offset >= 0:
                    order.append(all_pages[idx - offset])
            return order

        return all_pages

    def get_context_around(
        self,
        page_number: int,
        bbox: BoundingBox,
        words_before: int = 10,
        words_after: int = 10
    ) -> Tuple[str, str]:
        """Get text context before and after a bounding box.

        Args:
            page_number: Page number
            bbox: Bounding box of the target text
            words_before: Number of words to include before
            words_after: Number of words to include after

        Returns:
            Tuple of (text_before, text_after)
        """
        if page_number not in self.word_index:
            return ("", "")

        page_words = self.word_index[page_number]

        # Find words within the bbox
        target_words = []
        before_words = []
        after_words = []

        # Sort all words by reading order (top-to-bottom, left-to-right)
        sorted_words = sorted(page_words, key=lambda w: (-w.y1, w.x0))

        found_target = False
        for word in sorted_words:
            is_in_bbox = (
                word.x0 >= bbox.x0 - 5 and
                word.x1 <= bbox.x1 + 5 and
                word.y0 >= bbox.y0 - 5 and
                word.y1 <= bbox.y1 + 5
            )

            if is_in_bbox:
                target_words.append(word)
                found_target = True
            elif not found_target:
                before_words.append(word)
            else:
                after_words.append(word)

        # Get the last N words before and first N words after
        context_before = " ".join(w.text for w in before_words[-words_before:])
        context_after = " ".join(w.text for w in after_words[:words_after])

        return (context_before, context_after)


__all__ = [
    "CitationMapper",
    "MatchConfig",
]
