"""Analyzer for extracting signals from Markdown content.

This analyzer replaces pdfplumber-based extraction by using the structured Markdown 
output from Docling. It identifies headings, tables, and anchor phrases to 
provide signals for classification.
"""

import re
import hashlib
from typing import List, Optional, Dict
from app.models.page_analysis_models import PageSignals
from app.utils.logging import get_logger

logger = get_logger(__name__)

from typing import List, Optional, Dict, Tuple
from app.models.page_analysis_models import PageSignals, DocumentType

class MarkdownPageAnalyzer:
    """Analyzer for extracting signals from Markdown text."""

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
            PageSignals object
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
            additional_metadata=signal_metadata
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
