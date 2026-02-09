"""Footer extraction service for insurance documents.

This service extracts footer content from PDF pages, including endorsement form numbers,
policy numbers, and explicit continuation text. Uses Docling as the primary extraction
method with pypdfium2 as a fallback.

The extracted form numbers are crucial for linking multi-page endorsements, which is
more reliable than content-based continuation detection.
"""

import re
import io
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from functools import lru_cache

logger = logging.getLogger(__name__)

# Module-level singleton instance
_footer_extractor_instance: Optional["FooterExtractor"] = None


@dataclass
class FooterInfo:
    """Information extracted from a page's footer."""

    page_number: int
    form_number: Optional[str] = None  # e.g., "CA T3 53 02 15"
    policy_number: Optional[str] = None  # e.g., "BA-9M627065"
    explicit_continuation: Optional[str] = None  # e.g., "CONTINUATION OF FORM IL T4 05"
    page_number_text: Optional[str] = None  # e.g., "Page 1 of 3"
    raw_footer_items: List[str] = field(default_factory=list)

    def has_form_number(self) -> bool:
        """Check if this footer has a form number."""
        return self.form_number is not None

    def is_continuation(self) -> bool:
        """Check if this page is explicitly marked as a continuation."""
        return self.explicit_continuation is not None


class FooterExtractor:
    """Extract footer content including endorsement form numbers from PDF pages.

    Uses Docling as the primary extraction method with pypdfium2 as a fallback.
    Results are cached to avoid re-extracting for the same document.
    """

    # Regex patterns for endorsement form numbers
    # Pattern 1: CA/IL with T-codes (e.g., CA T4 52 02 16, IL T4 05 03 11)
    CA_IL_PATTERN = re.compile(r"\b(?:CA|IL)\s+T[34]\s+\d{2}\s+\d{2}\s+\d{2}\b")

    # Pattern 2: CG with D-codes (e.g., CG D6 04 08 13)
    CG_PATTERN = re.compile(r"\bCG\s+D[3-6]\s+\d{2}\s+\d{2}\s+\d{2}\b")

    # Pattern 3: WC codes (e.g., WC 42 06 01)
    WC_PATTERN = re.compile(r"\bWC\s+\d{2}\s+\d{2}\s+\d{2}\b")

    # Pattern 4: Generic 2-letter prefix pattern (fallback for other forms)
    GENERIC_ENDORSEMENT_PATTERN = re.compile(
        r"\b[A-Z]{2}\s+[A-Z\d]{1,3}\s+\d{2}\s+\d{2}(?:\s+\d{2})?\b"
    )

    # All endorsement patterns for iteration
    ENDORSEMENT_PATTERNS = [CA_IL_PATTERN, CG_PATTERN, WC_PATTERN, GENERIC_ENDORSEMENT_PATTERN]

    # Additional patterns
    COPYRIGHT_PATTERN = re.compile(r"©|Copyright|Insurance Services Office|rights reserved", re.I)
    PAGE_PATTERN = re.compile(r"Page\s+(\d+)(?:\s+of\s+(\d+))?", re.I)
    CONTINUATION_PATTERN = re.compile(r"CONTINUATION\s+OF\s+FORM\s+([A-Z]{2}\s+T?\d+.*?)(?:\s|$)", re.I)
    POLICY_NUMBER_PATTERN = re.compile(r"POLICY\s*(?:NUMBER|NO\.?)?[:\s]+([A-Z]{2}[-\s]?\d?[A-Z]?\d{6,})", re.I)

    def __init__(self):
        """Initialize the footer extractor."""
        self._cache: Dict[str, Dict[int, FooterInfo]] = {}
        logger.info("Initialized FooterExtractor")

    @classmethod
    def get_instance(cls) -> "FooterExtractor":
        """Get or create singleton instance of FooterExtractor."""
        global _footer_extractor_instance
        if _footer_extractor_instance is None:
            _footer_extractor_instance = cls()
        return _footer_extractor_instance

    def extract_footers(self, url_or_path: str) -> Dict[int, FooterInfo]:
        """Extract footer info including form numbers for each page.

        Args:
            url_or_path: URL or file path to the PDF document

        Returns:
            Dictionary mapping page numbers to FooterInfo
        """
        # Check cache first
        if url_or_path in self._cache:
            logger.debug(f"Using cached footer extraction for {url_or_path}")
            return self._cache[url_or_path]

        logger.info(f"Extracting footers from {url_or_path}")

        # Try Docling first, fall back to pypdfium2
        try:
            result = self._extract_with_docling(url_or_path)
        except Exception as e:
            logger.warning(f"Docling extraction failed: {e}, falling back to pypdfium2")
            result = self._extract_with_pypdfium(url_or_path)

        # Cache the result
        self._cache[url_or_path] = result
        return result

    def get_form_number(self, url_or_path: str, page_number: int) -> Optional[str]:
        """Get the endorsement form number for a specific page.

        Args:
            url_or_path: URL or file path to the PDF document
            page_number: Page number to get form number for

        Returns:
            Form number string if found, None otherwise
        """
        footers = self.extract_footers(url_or_path)
        if page_number in footers:
            return footers[page_number].form_number
        return None

    def get_page_form_numbers(self, url_or_path: str) -> Dict[int, str]:
        """Get form numbers for all pages that have them.

        Args:
            url_or_path: URL or file path to the PDF document

        Returns:
            Dictionary mapping page numbers to form numbers
        """
        footers = self.extract_footers(url_or_path)
        return {
            page_num: info.form_number
            for page_num, info in footers.items()
            if info.form_number
        }

    def find_endorsement_groups(self, url_or_path: str) -> Dict[str, List[int]]:
        """Find groups of pages that share the same form number.

        This is useful for identifying multi-page endorsements.

        Args:
            url_or_path: URL or file path to the PDF document

        Returns:
            Dictionary mapping form numbers to list of page numbers
        """
        form_numbers = self.get_page_form_numbers(url_or_path)
        groups: Dict[str, List[int]] = {}

        for page_num, form_number in form_numbers.items():
            if form_number not in groups:
                groups[form_number] = []
            groups[form_number].append(page_num)

        # Sort page numbers within each group
        for form_number in groups:
            groups[form_number].sort()

        return groups

    def clear_cache(self, url_or_path: Optional[str] = None):
        """Clear the extraction cache.

        Args:
            url_or_path: Specific URL to clear, or None to clear all
        """
        if url_or_path:
            self._cache.pop(url_or_path, None)
        else:
            self._cache.clear()

    def _extract_with_docling(self, url_or_path: str) -> Dict[int, FooterInfo]:
        """Extract footers using Docling.

        Args:
            url_or_path: URL or file path to the PDF document

        Returns:
            Dictionary mapping page numbers to FooterInfo
        """
        from docling.document_converter import DocumentConverter

        converter = DocumentConverter()
        result = converter.convert(url_or_path)
        doc = result.document

        # Dictionary to store footer items by page
        raw_footers_by_page: Dict[int, Dict[Tuple[float, float, str], str]] = {}

        for item, _ in doc.iterate_items():
            text = getattr(item, "text", "").strip()
            if not text:
                continue

            label = getattr(item, "label", None)

            # Get page and bbox info
            page_no = 1
            bbox = None
            page_height = 0

            if hasattr(item, "prov") and item.prov:
                prov = item.prov[0] if isinstance(item.prov, list) else item.prov
                page_no = getattr(prov, "page_no", 1)
                bbox = getattr(prov, "bbox", None)
                if hasattr(result, "pages") and page_no <= len(result.pages):
                    page_dim = result.pages[page_no - 1].size
                    if page_dim:
                        page_height = page_dim.height

            # Footer identification logic
            is_explicit_footer = (
                str(label) in {"page_footer", "DocItemLabel.PAGE_FOOTER"}
                or getattr(label, "name", None) == "PAGE_FOOTER"
            )

            is_at_bottom = False
            if bbox and page_height:
                top = getattr(bbox, "t", 0)
                bottom = getattr(bbox, "b", 0)
                # Items in bottom 35% of page are candidates
                if top > (0.65 * page_height) or bottom > (0.65 * page_height):
                    is_at_bottom = True

            is_endorsement = (
                any(pattern.search(text) for pattern in self.ENDORSEMENT_PATTERNS)
                or text.startswith("CA ")
            )
            is_copyright = bool(self.COPYRIGHT_PATTERN.search(text))
            is_page_num = bool(self.PAGE_PATTERN.search(text))

            if is_explicit_footer or is_at_bottom or is_endorsement or is_copyright or is_page_num:
                # Filter out long body text that happened to be at the bottom
                if (
                    is_at_bottom
                    and len(text) > 400
                    and not (is_endorsement or is_copyright or is_page_num or is_explicit_footer)
                ):
                    continue

                if page_no not in raw_footers_by_page:
                    raw_footers_by_page[page_no] = {}

                left = getattr(bbox, "l", 0) if bbox else 0
                top = getattr(bbox, "t", 0) if bbox else 0
                raw_footers_by_page[page_no][(top, left, text)] = text

        # Also try pypdfium2 for endorsement codes specifically (fallback extraction)
        try:
            pypdfium_footers = self._extract_with_pypdfium(url_or_path)
            for page_no, info in pypdfium_footers.items():
                if page_no not in raw_footers_by_page:
                    raw_footers_by_page[page_no] = {}
                for item in info.raw_footer_items:
                    # Add with high top coord to sort at bottom
                    raw_footers_by_page[page_no][(9999, len(raw_footers_by_page[page_no]), item)] = item
        except Exception as e:
            logger.debug(f"pypdfium2 fallback failed: {e}")

        # Convert raw footers to FooterInfo objects
        return self._process_raw_footers(raw_footers_by_page)

    def _extract_with_pypdfium(self, url_or_path: str) -> Dict[int, FooterInfo]:
        """Extract footers using pypdfium2.

        Args:
            url_or_path: URL or file path to the PDF document

        Returns:
            Dictionary mapping page numbers to FooterInfo
        """
        import pypdfium2 as pdfium
        import requests

        raw_footers_by_page: Dict[int, Dict[Tuple[float, float, str], str]] = {}

        # Load PDF data
        if url_or_path.startswith(("http://", "https://")):
            response = requests.get(url_or_path)
            pdf_data = io.BytesIO(response.content)
            pdf = pdfium.PdfDocument(pdf_data)
        else:
            pdf = pdfium.PdfDocument(url_or_path)

        try:
            for i in range(len(pdf)):
                page_no = i + 1
                page = pdf[i]
                text_page = page.get_textpage()

                try:
                    # pypdfium2 coordinate system: bottom-left (0,0)
                    # Get text from bottom 20% of page
                    width, height = page.get_size()
                    bottom_text = text_page.get_text_bounded(0, 0, width, height * 0.2).strip()

                    if bottom_text:
                        if page_no not in raw_footers_by_page:
                            raw_footers_by_page[page_no] = {}

                        # Look for all endorsement patterns
                        for pattern in self.ENDORSEMENT_PATTERNS:
                            matches = pattern.findall(bottom_text)
                            for match in matches:
                                match = match.strip()
                                raw_footers_by_page[page_no][
                                    (9999, len(raw_footers_by_page[page_no]), match)
                                ] = match

                        # Also store the raw bottom text for continuation detection
                        raw_footers_by_page[page_no][
                            (9998, 0, bottom_text[:200])
                        ] = bottom_text[:200]
                finally:
                    text_page.close()
                    page.close()
        finally:
            pdf.close()

        return self._process_raw_footers(raw_footers_by_page)

    def _process_raw_footers(
        self, raw_footers_by_page: Dict[int, Dict[Tuple[float, float, str], str]]
    ) -> Dict[int, FooterInfo]:
        """Process raw footer data into structured FooterInfo objects.

        Args:
            raw_footers_by_page: Raw footer data by page

        Returns:
            Dictionary mapping page numbers to FooterInfo
        """
        result: Dict[int, FooterInfo] = {}

        for page_no in sorted(raw_footers_by_page.keys()):
            # Sort items by vertical position (top to bottom), then horizontal (left to right)
            sorted_items = [v for k, v in sorted(raw_footers_by_page[page_no].items())]

            # Filter duplicates
            seen = set()
            unique_items = []
            for item in sorted_items:
                if item not in seen:
                    unique_items.append(item)
                    seen.add(item)

            # Extract structured data from footer items
            form_number = None
            policy_number = None
            explicit_continuation = None
            page_number_text = None

            combined_text = " | ".join(unique_items)

            # Find form number (prefer specific patterns over generic)
            for pattern in [self.CA_IL_PATTERN, self.CG_PATTERN, self.WC_PATTERN]:
                match = pattern.search(combined_text)
                if match:
                    form_number = match.group(0)
                    break

            # Fall back to generic pattern if no specific match
            if not form_number:
                match = self.GENERIC_ENDORSEMENT_PATTERN.search(combined_text)
                if match:
                    form_number = match.group(0)

            # Find policy number
            match = self.POLICY_NUMBER_PATTERN.search(combined_text)
            if match:
                policy_number = match.group(1)

            # Find explicit continuation
            match = self.CONTINUATION_PATTERN.search(combined_text)
            if match:
                explicit_continuation = f"CONTINUATION OF FORM {match.group(1)}"

            # Find page number text
            match = self.PAGE_PATTERN.search(combined_text)
            if match:
                if match.group(2):
                    page_number_text = f"Page {match.group(1)} of {match.group(2)}"
                else:
                    page_number_text = f"Page {match.group(1)}"

            result[page_no] = FooterInfo(
                page_number=page_no,
                form_number=form_number,
                policy_number=policy_number,
                explicit_continuation=explicit_continuation,
                page_number_text=page_number_text,
                raw_footer_items=unique_items,
            )

        return result


# Convenience function for quick form number extraction
def extract_form_numbers(url_or_path: str) -> Dict[int, str]:
    """Quick extraction of form numbers from a document.

    Args:
        url_or_path: URL or file path to the PDF document

    Returns:
        Dictionary mapping page numbers to form numbers
    """
    extractor = FooterExtractor.get_instance()
    return extractor.get_page_form_numbers(url_or_path)


# Convenience function for finding endorsement groups
def find_endorsement_groups(url_or_path: str) -> Dict[str, List[int]]:
    """Find groups of pages that share the same form number.

    Args:
        url_or_path: URL or file path to the PDF document

    Returns:
        Dictionary mapping form numbers to list of page numbers
    """
    extractor = FooterExtractor.get_instance()
    return extractor.find_endorsement_groups(url_or_path)
