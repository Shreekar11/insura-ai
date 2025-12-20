"""Lightweight page analyzer using pdfplumber for insurance document triage.

This analyzer extracts page-level signals without full OCR, enabling fast
classification and filtering of large insurance documents (100+ pages).
"""

import hashlib
import httpx
import pdfplumber
from typing import List, Optional
from pathlib import Path
from io import BytesIO
import time

from app.models.page_analysis_models import PageSignals
from app.utils.logging import get_logger

logger = get_logger(__name__)


class LightweightPageAnalyzer:
    """Analyzer for extracting lightweight signals from PDF pages using pdfplumber.
    
    This analyzer is designed to be:
    - Tolerant of complex/legacy PDFs
    - Fast (no full OCR)
    - Deterministic (layout-driven)
    - Suitable for page triage in insurance documents
    """
    
    def __init__(self):
        """Initialize LightweightPageAnalyzer."""
        logger.info("Initialized LightweightPageAnalyzer with pdfplumber backend")
    
    async def analyze_document(self, document_url: str) -> List[PageSignals]:
        """Analyze document and extract signals for all pages.
        
        Args:
            document_url: URL or local path to PDF document
            
        Returns:
            List of PageSignals objects (one per page)
            
        Raises:
            ValueError: If document processing fails
        """
        start_time = time.time()
        
        try:
            logger.info(
                "Starting lightweight page analysis",
                extra={
                    "document_url": document_url,
                    "analyzer": "pdfplumber"
                }
            )
            
            # Download or load PDF
            pdf_bytes = await self._load_pdf(document_url)
            load_time = time.time() - start_time
            
            logger.info(
                f"PDF loaded successfully in {load_time:.2f}s",
                extra={"size_bytes": len(pdf_bytes), "load_time_seconds": load_time}
            )
            
            # Open PDF with pdfplumber
            all_signals = []
            extraction_start = time.time()
            
            with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
                total_pages = len(pdf.pages)
                
                logger.info(
                    f"Document contains {total_pages} pages",
                    extra={"total_pages": total_pages}
                )
                
                # Extract signals from each page with progress tracking
                for page_num, page in enumerate(pdf.pages, start=1):
                    page_start = time.time()
                    signals = self._extract_page_signals(page, page_num)
                    all_signals.append(signals)
                    
                    # Log progress every 20 pages for large documents
                    if page_num % 20 == 0 or page_num == total_pages:
                        elapsed = time.time() - extraction_start
                        avg_time = elapsed / page_num
                        remaining = (total_pages - page_num) * avg_time
                        
                        logger.info(
                            f"Progress: {page_num}/{total_pages} pages analyzed "
                            f"({(page_num/total_pages)*100:.1f}%) - "
                            f"ETA: {remaining:.1f}s",
                            extra={
                                "pages_analyzed": page_num,
                                "total_pages": total_pages,
                                "progress_percent": (page_num/total_pages)*100,
                                "avg_time_per_page": avg_time,
                                "estimated_remaining_seconds": remaining
                            }
                        )
            
            total_time = time.time() - start_time
            extraction_time = time.time() - extraction_start
            
            # Summary statistics
            tables_count = sum(1 for s in all_signals if s.has_tables)
            avg_density = sum(s.text_density for s in all_signals) / len(all_signals)
            
            logger.info(
                f"✓ Page analysis complete: {len(all_signals)} pages in {total_time:.2f}s",
                extra={
                    "total_pages": len(all_signals),
                    "total_time_seconds": total_time,
                    "extraction_time_seconds": extraction_time,
                    "avg_time_per_page": extraction_time / len(all_signals),
                    "pages_with_tables": tables_count,
                    "avg_text_density": round(avg_density, 3)
                }
            )
            
            return all_signals
            
        except Exception as e:
            logger.error(
                f"✗ Page analysis failed: {e}",
                extra={
                    "document_url": document_url,
                    "error_type": type(e).__name__
                },
                exc_info=True
            )
            raise ValueError(f"Failed to analyze document: {e}") from e
    
    async def _load_pdf(self, document_url: str) -> bytes:
        """Load PDF from URL or local path.
        
        Args:
            document_url: URL or local path to PDF
            
        Returns:
            PDF bytes
        """
        is_url = document_url.startswith(('http://', 'https://'))
        
        if is_url:
            logger.debug(
                "Downloading PDF from URL",
                extra={"url": document_url, "source": "remote"}
            )
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.get(document_url)
                response.raise_for_status()
                
                logger.debug(
                    f"Downloaded {len(response.content)} bytes",
                    extra={"size_bytes": len(response.content)}
                )
                return response.content
        else:
            logger.debug(
                "Loading PDF from local filesystem",
                extra={"path": document_url, "source": "local"}
            )
            path = Path(document_url)
            if not path.exists():
                raise FileNotFoundError(f"PDF file not found: {document_url}")
            return path.read_bytes()
    
    def _extract_page_signals(self, page, page_num: int) -> PageSignals:
        """Extract signals from a single page.
        
        Args:
            page: pdfplumber page object
            page_num: Page number (1-indexed)
            
        Returns:
            PageSignals object
        """
        top_lines = self._extract_top_lines(page)
        text_density = self._calculate_text_density(page)
        has_tables = self._detect_tables(page)
        max_font_size = self._estimate_max_font_size(page)
        
        page_text = page.extract_text() or ""
        page_hash = self._generate_page_hash(page_text)
        
        logger.debug(
            f"Page {page_num} signals extracted",
            extra={
                "page_number": page_num,
                "top_lines_count": len(top_lines),
                "text_density": text_density,
                "has_tables": has_tables,
                "max_font_size": max_font_size,
                "text_length": len(page_text)
            }
        )
        
        return PageSignals(
            page_number=page_num,
            top_lines=top_lines,
            text_density=text_density,
            has_tables=has_tables,
            max_font_size=max_font_size,
            page_hash=page_hash
        )
    
    def _extract_top_lines(self, page) -> List[str]:
        """Extract top lines from page (header area).
        
        Args:
            page: pdfplumber page object
            
        Returns:
            List of top lines (up to 10)
        """
        try:
            page_height = page.height
            top_threshold = page_height * 0.2
            
            text = page.extract_text()
            if not text:
                return []
            
            words = page.extract_words()
            top_words = [w for w in words if w['top'] < top_threshold]
            top_words.sort(key=lambda w: (w['top'], w['x0']))
            
            lines = []
            current_line = []
            current_y = None
            y_tolerance = 5
            
            for word in top_words:
                if current_y is None or abs(word['top'] - current_y) < y_tolerance:
                    current_line.append(word['text'])
                    current_y = word['top']
                else:
                    if current_line:
                        lines.append(' '.join(current_line))
                    current_line = [word['text']]
                    current_y = word['top']
            
            if current_line:
                lines.append(' '.join(current_line))
            
            top_lines = [line.strip() for line in lines if line.strip()][:10]
            return top_lines
            
        except Exception as e:
            logger.warning(
                f"Top lines extraction failed, using fallback: {e}",
                extra={"error_type": type(e).__name__}
            )
            text = page.extract_text() or ""
            lines = text.split('\n')
            return [line.strip() for line in lines if line.strip()][:10]
    
    def _calculate_text_density(self, page) -> float:
        """Calculate text density from character positions.
        
        Args:
            page: pdfplumber page object
            
        Returns:
            Text density ratio (0.0 to 1.0)
        """
        try:
            page_area = page.width * page.height
            if page_area == 0:
                return 0.0
            
            chars = page.chars
            if not chars:
                return 0.0
            
            text_area = sum(
                char.get('width', 0) * char.get('height', 0)
                for char in chars
            )
            
            density = min(text_area / page_area, 1.0)
            return round(density, 3)
            
        except Exception as e:
            logger.warning(
                f"Text density calculation failed: {e}",
                extra={"error_type": type(e).__name__}
            )
            return 0.5
    
    def _detect_tables(self, page) -> bool:
        """Detect table presence using layout analysis.
        
        Args:
            page: pdfplumber page object
            
        Returns:
            True if tables detected, False otherwise
        """
        try:
            tables = page.find_tables()
            return len(tables) > 0
        except Exception as e:
            logger.debug(
                f"Table detection failed: {e}",
                extra={"error_type": type(e).__name__}
            )
            return False
    
    def _estimate_max_font_size(self, page) -> Optional[float]:
        """Estimate max font size from character metadata.
        
        Args:
            page: pdfplumber page object
            
        Returns:
            Estimated max font size or None
        """
        try:
            chars = page.chars
            if not chars:
                return None
            
            font_sizes = [
                char.get('height', 0)
                for char in chars
                if char.get('height', 0) > 0
            ]
            
            if not font_sizes:
                return None
            
            max_size = max(font_sizes)
            return round(max_size, 1)
            
        except Exception as e:
            logger.debug(
                f"Font size estimation failed: {e}",
                extra={"error_type": type(e).__name__}
            )
            return None
    
    def _generate_page_hash(self, text: str) -> str:
        """Generate hash of page content for duplicate detection.
        
        Args:
            text: Page text content
            
        Returns:
            SHA256 hash (first 16 characters)
        """
        normalized = ' '.join(text.lower().split())
        hash_obj = hashlib.sha256(normalized.encode('utf-8'))
        return hash_obj.hexdigest()[:16]
