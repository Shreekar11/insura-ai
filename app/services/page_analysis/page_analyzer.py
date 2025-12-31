"""Page analyzer service using pdfplumber for lightweight signal extraction.

This service extracts lightweight signals from PDF pages without performing full OCR,
enabling fast page classification and filtering.
"""

from typing import List, Optional
from app.services.page_analysis.lightweight_page_analyzer import LightweightPageAnalyzer
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
        """Initialize PageAnalyzer with pdfplumber-based analyzer."""
        self.analyzer = LightweightPageAnalyzer.get_instance()
        logger.info("Initialized PageAnalyzer with pdfplumber backend")
    
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
        """Analyze full document and extract signals for all pages.
        
        Args:
            document_url: URL or path to PDF document
            
        Returns:
            List of PageSignals objects (one per page)
            
        Raises:
            ValueError: If document processing fails
        """
        return await self.analyzer.analyze_document(document_url)
