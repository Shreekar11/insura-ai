"""Page analyzer service using pdfplumber for lightweight signal extraction.

This service extracts lightweight signals from PDF pages without performing full OCR,
enabling fast page classification and filtering.

MIGRATED: Now uses pdfplumber instead of Docling for better tolerance of complex PDFs.
"""

from typing import List
from app.services.pipeline.lightweight_page_analyzer import LightweightPageAnalyzer
from app.models.page_analysis_models import PageSignals
from app.utils.logging import get_logger

logger = get_logger(__name__)


class PageAnalyzer:
    """Analyzer for extracting lightweight signals from PDF pages.
    
    Uses pdfplumber for fast, tolerant page signal extraction without full OCR.
    This is a wrapper around LightweightPageAnalyzer for backward compatibility.
    """
    
    def __init__(self):
        """Initialize PageAnalyzer with pdfplumber-based analyzer."""
        self.analyzer = LightweightPageAnalyzer()
        logger.info("Initialized PageAnalyzer with pdfplumber backend")

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
