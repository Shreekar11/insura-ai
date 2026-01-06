"""Page analyzer service using pdfplumber for lightweight signal extraction.

This service extracts lightweight signals from PDF pages without performing full OCR,
enabling fast page classification and filtering.
"""

from typing import List, Optional
from app.services.processed.services.analysis.lightweight_page_analyzer import LightweightPageAnalyzer
from app.services.processed.services.analysis.markdown_page_analyzer import MarkdownPageAnalyzer
from app.models.page_analysis_models import PageSignals
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Module-level singleton instance
_page_analyzer_instance: Optional["PageAnalyzer"] = None


class PageAnalyzer:
    """Analyzer for extracting lightweight signals from PDF pages.
    
    Uses pdfplumber for fast, tolerant page signal extraction without full OCR.
    This is a wrapper around LightweightPageAnalyzer for backward compatibility.
    """
    
    def __init__(self):
        """Initialize PageAnalyzer with backends."""
        self.pdf_analyzer = LightweightPageAnalyzer.get_instance()
        self.markdown_analyzer = MarkdownPageAnalyzer()
        logger.info("Initialized PageAnalyzer with PDF and Markdown backends")
    
    @classmethod
    def get_instance(cls) -> "PageAnalyzer":
        """Get or create singleton instance of PageAnalyzer.
        
        Returns:
            Singleton instance of PageAnalyzer
        """
        global _page_analyzer_instance
        if _page_analyzer_instance is None:
            _page_analyzer_instance = cls()
        return _page_analyzer_instance

    async def analyze_document(self, document_url: str) -> List[PageSignals]:
        """Analyze full document and extract signals for all pages (using PDF)."""
        return await self.pdf_analyzer.analyze_document(document_url)

    def analyze_markdown(self, markdown_content: str, page_number: int) -> PageSignals:
        """Analyze markdown content for a specific page."""
        return self.markdown_analyzer.analyze_markdown(markdown_content, page_number)

    def analyze_markdown_batch(self, pages: List[tuple[str, int]]) -> List[PageSignals]:
        """Analyze multiple markdown pages."""
        return [self.analyze_markdown(content, num) for content, num in pages]
