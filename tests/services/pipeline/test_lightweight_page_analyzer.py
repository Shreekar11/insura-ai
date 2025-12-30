"""Unit tests for LightweightPageAnalyzer using pdfplumber.

Tests the pdfplumber-based page signal extraction for insurance documents.
"""

import pytest
from typing import List
from app.services.page_analysis.lightweight_page_analyzer import LightweightPageAnalyzer
from app.models.page_analysis_models import PageSignals


# Harbor Cove Property Policy 2020 - public test document
HARBOR_COVE_PDF_URL = "https://ujrhkyqkoasuxcpfzeyr.supabase.co/storage/v1/object/public/docs/Harbor-Cove-Property-Policy-2020.pdf"


class TestLightweightPageAnalyzer:
    """Test suite for LightweightPageAnalyzer."""
    
    @pytest.fixture
    def analyzer(self):
        """Create analyzer instance."""
        return LightweightPageAnalyzer()
    
    def test_analyzer_initialization(self, analyzer):
        """Test that analyzer initializes correctly."""
        assert analyzer is not None
        assert hasattr(analyzer, 'analyze_document')
    
    @pytest.mark.asyncio
    async def test_analyze_document_basic(self, analyzer):
        """Test basic document analysis with Harbor Cove PDF."""
        signals = await analyzer.analyze_document(HARBOR_COVE_PDF_URL)
        
        # Should return a list of PageSignals
        assert isinstance(signals, list)
        assert len(signals) > 0
        
        # Each item should be a PageSignals object
        for signal in signals:
            assert isinstance(signal, PageSignals)
            assert signal.page_number > 0
            assert isinstance(signal.top_lines, list)
            assert isinstance(signal.text_density, float)
            assert 0.0 <= signal.text_density <= 1.0
            assert isinstance(signal.has_tables, bool)
            assert isinstance(signal.page_hash, str)
    
    @pytest.mark.asyncio
    async def test_top_lines_extraction(self, analyzer):
        """Test that top lines are extracted correctly."""
        signals = await analyzer.analyze_document(HARBOR_COVE_PDF_URL)
        
        # Check first page signals
        first_page = signals[0]
        assert len(first_page.top_lines) > 0
        assert len(first_page.top_lines) <= 10  # Should be limited to ~10 lines
        
        # Top lines should be non-empty strings
        for line in first_page.top_lines:
            assert isinstance(line, str)
            assert len(line.strip()) > 0
    
    @pytest.mark.asyncio
    async def test_text_density_calculation(self, analyzer):
        """Test text density calculation."""
        signals = await analyzer.analyze_document(HARBOR_COVE_PDF_URL)
        
        # All pages should have valid density values
        for signal in signals:
            assert 0.0 <= signal.text_density <= 1.0
            
        # At least some pages should have non-zero density
        densities = [s.text_density for s in signals]
        assert any(d > 0.0 for d in densities)
    
    @pytest.mark.asyncio
    async def test_table_detection(self, analyzer):
        """Test table detection on pages."""
        signals = await analyzer.analyze_document(HARBOR_COVE_PDF_URL)
        
        # Check that has_tables is a boolean for all pages
        for signal in signals:
            assert isinstance(signal.has_tables, bool)
        
        # Harbor Cove likely has some tables (schedules, coverages)
        # At least one page should have tables
        has_any_tables = any(s.has_tables for s in signals)
        assert has_any_tables, "Expected at least one page with tables in insurance document"
    
    @pytest.mark.asyncio
    async def test_font_size_estimation(self, analyzer):
        """Test font size estimation."""
        signals = await analyzer.analyze_document(HARBOR_COVE_PDF_URL)
        
        # Check that font sizes are extracted where available
        font_sizes = [s.max_font_size for s in signals if s.max_font_size is not None]
        
        # Should have font size data for at least some pages
        assert len(font_sizes) > 0
        
        # Font sizes should be reasonable (typically 8-24pt for documents)
        for size in font_sizes:
            assert 6.0 <= size <= 72.0, f"Font size {size} outside expected range"
    
    @pytest.mark.asyncio
    async def test_page_hash_generation(self, analyzer):
        """Test page hash generation for duplicate detection."""
        signals = await analyzer.analyze_document(HARBOR_COVE_PDF_URL)
        
        # All pages should have hashes
        for signal in signals:
            assert signal.page_hash is not None
            assert len(signal.page_hash) > 0
            assert isinstance(signal.page_hash, str)
        
        # Hashes should be unique for different pages (mostly)
        hashes = [s.page_hash for s in signals]
        unique_hashes = set(hashes)
        
        # Allow for some duplicates (e.g., blank pages, repeated clauses)
        # but most should be unique
        uniqueness_ratio = len(unique_hashes) / len(hashes)
        assert uniqueness_ratio > 0.5, "Too many duplicate page hashes"
    
    @pytest.mark.asyncio
    async def test_page_number_sequence(self, analyzer):
        """Test that page numbers are sequential."""
        signals = await analyzer.analyze_document(HARBOR_COVE_PDF_URL)
        
        page_numbers = [s.page_number for s in signals]
        
        # Should start at 1
        assert page_numbers[0] == 1
        
        # Should be sequential
        for i, page_num in enumerate(page_numbers, start=1):
            assert page_num == i
    
    @pytest.mark.asyncio
    async def test_invalid_url_handling(self, analyzer):
        """Test error handling for invalid URLs."""
        with pytest.raises(Exception):  # Should raise ValueError or similar
            await analyzer.analyze_document("https://invalid-url-that-does-not-exist.com/fake.pdf")
    
    @pytest.mark.asyncio
    async def test_non_pdf_url_handling(self, analyzer):
        """Test error handling for non-PDF URLs."""
        with pytest.raises(Exception):
            await analyzer.analyze_document("https://www.google.com")
    
    @pytest.mark.asyncio
    async def test_insurance_specific_signals(self, analyzer):
        """Test that insurance-specific signals are captured."""
        signals = await analyzer.analyze_document(HARBOR_COVE_PDF_URL)
        
        # Combine all top lines from all pages
        all_top_lines = []
        for signal in signals:
            all_top_lines.extend(signal.top_lines)
        
        all_text = " ".join(all_top_lines).lower()
        
        # Should contain insurance-related keywords
        insurance_keywords = ["policy", "coverage", "insured", "premium", "deductible"]
        found_keywords = [kw for kw in insurance_keywords if kw in all_text]
        
        assert len(found_keywords) > 0, "Expected to find insurance-related keywords in top lines"
