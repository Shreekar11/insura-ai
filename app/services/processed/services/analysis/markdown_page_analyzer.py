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

    def analyze_markdown(self, markdown_content: str, page_number: int) -> PageSignals:
        """Analyze markdown content for a specific page.
        
        Args:
            markdown_content: Markdown text for the page
            page_number: Page number being analyzed
            
        Returns:
            PageSignals object
        """
        # Extract headings (# , ## , ### )
        headings = self._extract_headings(markdown_content)
        
        # Extract top lines (first 10 lines)
        top_lines = self._extract_top_lines(markdown_content)
        
        # Detect tables (Markdown table syntax |---|)
        has_tables = self._detect_tables(markdown_content)
        
        # Calculate text density (relative to average page length)
        text_density = self._calculate_text_density(markdown_content)
        
        # Generate page hash for duplicate detection
        page_hash = self._generate_page_hash(markdown_content)
        
        # Estimated max font size (Markdown headers give a hint)
        max_font_size = self._estimate_max_font_size(markdown_content)

        return PageSignals(
            page_number=page_number,
            top_lines=headings if headings else top_lines,
            text_density=text_density,
            has_tables=has_tables,
            max_font_size=max_font_size,
            page_hash=page_hash,
            metadata={
                "source": "markdown",
                "headings_found": len(headings),
                "anchor_phrases_found": self._find_anchor_phrases(markdown_content)
            }
        )

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
