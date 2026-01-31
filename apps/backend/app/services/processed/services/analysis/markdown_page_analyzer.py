"""Analyzer for extracting signals from Markdown content.

This analyzer replaces pdfplumber-based extraction by using the structured Markdown
output from Docling. It identifies headings, tables, and anchor phrases to
provide signals for classification.

Includes endorsement continuation detection signals:
- Mid-sentence start detection
- Section label sequence detection (A, B, C -> D, E, F)
- Explicit continuation text detection
- Policy/form number extraction
"""

import re
import hashlib
from typing import List, Optional, Dict, Tuple, Any
from app.models.page_analysis_models import PageSignals, DocumentType
from app.utils.logging import get_logger

logger = get_logger(__name__)

class MarkdownPageAnalyzer:
    """Analyzer for extracting signals from Markdown text.

    Includes endorsement continuation detection for cross-page endorsement tracking.
    """

    # Policy number patterns (more reliable than form numbers)
    POLICY_NUMBER_PATTERNS = [
        r'Policy\s*(?:Number|No\.?)[:\s]+([A-Z]{2}[-\s]?\d?[A-Z]?\d{6,})',
        r'POLICY\s*NUMBER[:\s]+([A-Z]{2}[-\s]?\d?[A-Z]?\d{6,})',
        r'Policy\s*#[:\s]*([A-Z0-9\-]+)',
    ]

    # Form number patterns (less reliable - often in footers not extracted)
    FORM_NUMBER_PATTERNS = [
        r'(?:Form\s+)?([A-Z]{2}\s+[A-Z]?\d\s+\d{2}\s+\d{2}\s+\d{2})',  # IL T4 05 03 11
        r'([A-Z]{2}\s+[A-Z]\d\s+\d{2}\s+\d{2}\s+\d{2})',  # CG D3 16 11 11
    ]

    # Section label patterns (A., B., C., 1., 2., etc.)
    SECTION_LABEL_PATTERNS = [
        r'^##?\s*([A-Z])\.?\s+[A-Z]',  # "## A. BROAD FORM" in markdown
        r'^-?\s*([A-Z])\.?\s+[A-Z]',   # "- A. Some text" or "A. Some text"
        r'^##?\s*(\d+)\.?\s+[A-Z]',    # "## 1. First provision"
    ]

    # Endorsement header patterns
    ENDORSEMENT_HEADER_PATTERNS = [
        r'THIS\s+ENDORSEMENT\s+CHANGES\s+THE\s+POLICY',
        r'PLEASE\s+READ\s+(THIS\s+ENDORSEMENT\s+)?CAREFULLY',
        r'THIS\s+ENDORSEMENT\s+MODIFIES\s+INSURANCE',
        r'ATTACHED\s+TO\s+AND\s+FORMS?\s+PART\s+OF',
    ]

    # Explicit continuation patterns
    EXPLICIT_CONTINUATION_PATTERNS = [
        r'\(CONTINUED\s+ON\s+[^)]+\)',
        r'CONTINUATION\s+OF\s+(?:FORM\s+)?[A-Z\d\s]+',
        r'(?:continued|cont[\'.]?d)\s+(?:from|on)\s+(?:previous|next)',
    ]

    def __init__(self):
        """Initialize MarkdownPageAnalyzer."""
        # Common insurance patterns for signal extraction
        self.ANCHOR_PHRASES = [
            "DECLARATIONS", "POLICY NUMBER", "INSURED", "PREMIUM",
            "COVERAGE", "LIMITS OF LIABILITY", "DEDUCTIBLE",
            "CONDITIONS", "EXCLUSIONS", "ENDORSEMENT",
            "SCHEDULE OF VALUES", "SOV", "LOSS RUN", "CLAIMS HISTORY",
            "DEFINITIONS", "TABLE OF CONTENTS"
        ]

        # Enhance with document type detection patterns
        self.DOCUMENT_TYPE_PATTERNS = {
            DocumentType.POLICY: [
                "DECLARATIONS", "COVERAGE", "LIMITS OF LIABILITY",
                "POLICY NUMBER", "EFFECTIVE DATE", "EXPIRATION DATE"
            ],
            DocumentType.SOV: [
                "SCHEDULE OF VALUES", "SOV", "PROPERTY VALUATION",
                "BUILDING VALUE", "CONTENTS VALUE"
            ],
            DocumentType.LOSS_RUN: [
                "LOSS HISTORY", "CLAIMS", "LOSS RUN", "CLAIM DATE",
                "LOSS DATE", "AMOUNT PAID"
            ],
            DocumentType.ENDORSEMENT: [
                "ENDORSEMENT", "AMENDMENT", "RIDER", "ATTACHMENT"
            ],
            DocumentType.ACORD_APPLICATION: [
                "ACORD", "APPLICANT INFORMATION", "PRODUCER INFORMATION",
                "REQUESTED COVERAGE", "PRIOR CARRIER", "LOSS HISTORY"
            ],
            DocumentType.PROPOSAL: [
                "PROPOSAL", "WE RECOMMEND", "OUR RECOMMENDATION",
                "SUMMARY OF COVERAGE OPTIONS", "PRESENTED FOR YOUR REVIEW"
            ],
        }

    def analyze_markdown_batch(
        self, 
        pages: List[tuple[str, int]]
    ) -> List[PageSignals]:
        """Batch analyze markdown pages with document type detection."""
        signals_list = []
        
        for content, page_num in pages:
            signals = self.analyze_markdown(content, page_num)
            signals_list.append(signals)
        
        return signals_list
    
    def detect_document_type(
        self, 
        all_markdown: str
    ) -> Tuple[DocumentType, float]:
        """Detect document type from content patterns."""
        scores = {}
        upper_content = all_markdown.upper()
        
        for doc_type, keywords in self.DOCUMENT_TYPE_PATTERNS.items():
            match_count = sum(1 for kw in keywords if kw in upper_content)
            scores[doc_type] = match_count / len(keywords) if keywords else 0.0
        
        if not scores:
             return DocumentType.UNKNOWN, 0.0

        best_type = max(scores, key=scores.get)
        confidence = scores[best_type]
        
        return best_type, confidence

    def analyze_markdown(
        self,
        markdown_content: str,
        page_number: int,
        metadata: Optional[Dict[str, Any]] = None
    ) -> PageSignals:
        """Analyze markdown content for a specific page.

        Args:
            markdown_content: Markdown text for the page
            page_number: Page number being analyzed
            metadata: Optional structural metadata from Docling

        Returns:
            PageSignals object with continuation detection signals
        """
        metadata = metadata or {}

        # Extract headings (# , ## , ### ) - fallback if no metadata
        headings = self._extract_headings(markdown_content)

        # Extract top lines (first 10 lines)
        top_lines = self._extract_top_lines(markdown_content)

        # Detect tables (Prefer metadata if available)
        has_tables = metadata.get("has_tables", self._detect_tables(markdown_content))

        # Calculate text density (Prefer metadata-aware density)
        text_density = self._calculate_text_density_enhanced(markdown_content, metadata)

        # Generate page hash for duplicate detection
        page_hash = self._generate_page_hash(markdown_content)

        # Estimated max font size (Prefer metadata if available)
        max_font_size = metadata.get("max_font_size", self._estimate_max_font_size(markdown_content))

        # === ENDORSEMENT CONTINUATION DETECTION SIGNALS ===
        # Extract policy number
        policy_number = self._extract_policy_number(markdown_content)

        # Extract form number (often unavailable)
        form_number = self._extract_form_number(markdown_content)

        # Check for endorsement header
        has_endorsement_header = self._has_endorsement_header(markdown_content)

        # Detect mid-sentence start
        starts_mid_sentence, first_line_text = self._detect_mid_sentence_start(markdown_content)

        # Extract section labels (A., B., C., etc.)
        section_labels, last_section_label = self._extract_section_labels(markdown_content)

        # Check for explicit continuation text
        explicit_continuation = self._extract_explicit_continuation(markdown_content)

        # Build signal metadata
        signal_metadata = {
            "source": "docling" if metadata else "markdown",
            "headings_found": len(headings),
            "anchor_phrases_found": self._find_anchor_phrases(markdown_content)
        }

        # Merge relevant Docling metadata into signals for classification logic
        if metadata:
            signal_metadata.update({
                "block_count": metadata.get("block_count"),
                "text_block_count": metadata.get("text_block_count"),
                "table_block_count": metadata.get("table_block_count"),
                "structure_type": metadata.get("structure_type"),
                "heading_levels": metadata.get("heading_levels", [])
            })

        return PageSignals(
            page_number=page_number,
            top_lines=headings if headings else top_lines,
            all_lines=markdown_content.split('\n'),
            text_density=text_density,
            has_tables=has_tables,
            max_font_size=max_font_size,
            page_hash=page_hash,
            additional_metadata=signal_metadata,
            # Continuation detection signals
            policy_number=policy_number,
            form_number=form_number,
            has_endorsement_header=has_endorsement_header,
            starts_mid_sentence=starts_mid_sentence,
            first_line_text=first_line_text,
            section_labels=section_labels,
            last_section_label=last_section_label,
            explicit_continuation=explicit_continuation,
        )

    def _calculate_text_density_enhanced(self, text: str, metadata: Dict[str, Any]) -> float:
        """Enhanced text density calculation using structural metadata."""
        if not metadata:
            return self._calculate_text_density(text)
            
        # Using block count as a proxy for density if text exists
        # 20 blocks is roughly 1.0 density
        block_count = metadata.get("block_count", 0)
        char_density = min(len(text) / 4000.0, 1.0)
        
        block_density = min(block_count / 25.0, 1.0)
        
        # Weighted average: 60% char-based, 40% block-based
        return round((char_density * 0.6) + (block_density * 0.4), 3)


    def _extract_headings(self, text: str) -> List[str]:
        """Extract Markdown headings."""
        headings = re.findall(r'^#{1,6}\s+(.+)$', text, re.MULTILINE)
        return [h.strip() for h in headings if h.strip()]

    def _extract_top_lines(self, text: str) -> List[str]:
        """Extract first 10 non-empty lines."""
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        return lines[:10]

    def _detect_tables(self, text: str) -> bool:
        """Detect if Markdown tables exist."""
        # Simple pattern for markdown table separator line
        return bool(re.search(r'\|[-:\s|]+\|', text))

    def _calculate_text_density(self, text: str) -> float:
        """Heuristic for text density based on length."""
        # Assume 4000 characters is 1.0 density
        return min(len(text) / 4000.0, 1.0)

    def _generate_page_hash(self, text: str) -> str:
        """Generate SHA256 hash of normalized text."""
        normalized = ' '.join(text.lower().split())
        return hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:16]

    def _estimate_max_font_size(self, text: str) -> float:
        """Map Markdown headers to estimated font sizes."""
        if "# " in text: return 24.0
        if "## " in text: return 20.0
        if "### " in text: return 16.0
        return 11.0

    def _find_anchor_phrases(self, text: str) -> List[str]:
        """Find common insurance anchor phrases."""
        found = []
        upper_text = text.upper()
        for phrase in self.ANCHOR_PHRASES:
            if phrase in upper_text:
                found.append(phrase)
        return found

    # === ENDORSEMENT CONTINUATION DETECTION METHODS ===

    def _extract_policy_number(self, text: str) -> Optional[str]:
        """Extract policy number from page text."""
        for pattern in self.POLICY_NUMBER_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).upper().replace(' ', '-')
        return None

    def _extract_form_number(self, text: str) -> Optional[str]:
        """Extract form number from page text (often unavailable in markdown)."""
        for pattern in self.FORM_NUMBER_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).upper()
        return None

    def _has_endorsement_header(self, text: str) -> bool:
        """Check if page has endorsement header."""
        for pattern in self.ENDORSEMENT_HEADER_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    def _detect_mid_sentence_start(self, text: str) -> Tuple[bool, Optional[str]]:
        """Detect if page starts mid-sentence.

        Indicators:
        - First line starts with lowercase letter
        - First line starts with punctuation continuation (comma, completing thought)
        - First line is a sentence fragment

        Returns:
            Tuple of (starts_mid_sentence, first_line_text)
        """
        lines = text.split('\n')

        # Find first non-empty, non-comment, non-markdown-heading line
        first_line = None
        for line in lines:
            stripped = line.strip()
            # Skip empty lines, markdown comments, and pure markdown headings
            if stripped and not stripped.startswith('<!--') and not stripped.startswith('#'):
                # Remove bullet points and list markers for analysis
                content = re.sub(r'^[-*•]\s*', '', stripped)
                if content:
                    first_line = content
                    break

        if not first_line:
            return (False, None)

        # Check for mid-sentence indicators
        mid_sentence_indicators = [
            # Starts with lowercase letter
            first_line[0].islower() if first_line else False,
            # Starts with conjunction
            bool(re.match(r'^(and|or|but|however|therefore|moreover|furthermore|also)\b', first_line, re.IGNORECASE) and first_line[0].islower()),
            # Starts with punctuation that completes a thought
            first_line.startswith((',', ')', ']')),
        ]

        return (any(mid_sentence_indicators), first_line)

    def _extract_section_labels(self, text: str) -> Tuple[List[str], Optional[str]]:
        """Extract section labels (A., B., C., 1., 2., etc.) from page.

        Returns:
            Tuple of (all_labels_found, last_label_on_page)
        """
        labels = []
        for pattern in self.SECTION_LABEL_PATTERNS:
            matches = re.findall(pattern, text, re.MULTILINE)
            labels.extend(matches)

        # Deduplicate while preserving order
        seen = set()
        unique_labels = []
        for label in labels:
            if label not in seen:
                seen.add(label)
                unique_labels.append(label)

        last_label = unique_labels[-1] if unique_labels else None
        return (unique_labels, last_label)

    def _extract_explicit_continuation(self, text: str) -> Optional[str]:
        """Extract explicit continuation references."""
        for pattern in self.EXPLICIT_CONTINUATION_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(0)
        return None
