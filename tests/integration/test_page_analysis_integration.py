"""Integration tests for page analysis workflow.

Tests the complete page analysis pipeline from signal extraction
through classification to manifest generation.
"""

import pytest
from uuid import uuid4
from app.services.pipeline.lightweight_page_analyzer import LightweightPageAnalyzer
from app.services.pipeline.page_classifier import PageClassifier
from app.services.pipeline.duplicate_detector import DuplicateDetector
from app.models.page_analysis_models import PageSignals, PageClassification, PageManifest, PageType


# Harbor Cove Property Policy 2020 - public test document
HARBOR_COVE_PDF_URL = "https://ujrhkyqkoasuxcpfzeyr.supabase.co/storage/v1/object/public/docs/Harbor-Cove-Property-Policy-2020.pdf"


class TestPageAnalysisIntegration:
    """Integration tests for the complete page analysis pipeline."""
    
    @pytest.fixture
    def analyzer(self):
        """Create analyzer instance."""
        return LightweightPageAnalyzer()
    
    @pytest.fixture
    def classifier(self):
        """Create classifier instance."""
        return PageClassifier()
    
    @pytest.fixture
    def duplicate_detector(self):
        """Create duplicate detector instance."""
        return DuplicateDetector()
    
    @pytest.mark.asyncio
    async def test_end_to_end_page_analysis(self, analyzer, classifier, duplicate_detector):
        """Test complete page analysis workflow."""
        # Step 1: Extract signals
        signals = await analyzer.analyze_document(HARBOR_COVE_PDF_URL)
        assert len(signals) > 0
        
        # Step 2: Classify pages
        classifications = []
        for signal in signals:
            # Check for duplicates
            is_dup, dup_of = duplicate_detector.is_duplicate(signal)
            
            if is_dup:
                classification = PageClassification(
                    page_number=signal.page_number,
                    page_type=PageType.DUPLICATE,
                    confidence=1.0,
                    should_process=False,
                    duplicate_of=dup_of,
                    reasoning=f"Duplicate of page {dup_of}"
                )
            else:
                classification = classifier.classify(signal)
            
            classifications.append(classification)
        
        assert len(classifications) == len(signals)
        
        # Step 3: Create manifest
        document_id = uuid4()
        pages_to_process = [c.page_number for c in classifications if c.should_process]
        pages_skipped = [c.page_number for c in classifications if not c.should_process]
        
        manifest = PageManifest(
            document_id=document_id,
            total_pages=len(classifications),
            pages_to_process=pages_to_process,
            pages_skipped=pages_skipped,
            classifications=classifications
        )
        
        # Verify manifest
        assert manifest.total_pages == len(signals)
        assert len(manifest.pages_to_process) + len(manifest.pages_skipped) == manifest.total_pages
        assert 0.0 <= manifest.processing_ratio <= 1.0
    
    @pytest.mark.asyncio
    async def test_processing_ratio_target(self, analyzer, classifier, duplicate_detector):
        """Test that processing ratio meets target (15-30%)."""
        signals = await analyzer.analyze_document(HARBOR_COVE_PDF_URL)
        
        classifications = []
        for signal in signals:
            is_dup, dup_of = duplicate_detector.is_duplicate(signal)
            
            if is_dup:
                classification = PageClassification(
                    page_number=signal.page_number,
                    page_type=PageType.DUPLICATE,
                    confidence=1.0,
                    should_process=False,
                    duplicate_of=dup_of,
                    reasoning=f"Duplicate of page {dup_of}"
                )
            else:
                classification = classifier.classify(signal)
            
            classifications.append(classification)
        
        pages_to_process = [c.page_number for c in classifications if c.should_process]
        processing_ratio = len(pages_to_process) / len(classifications)
        
        # Target: 15-30% of pages should be processed
        # Allow some flexibility for different document structures
        assert 0.10 <= processing_ratio <= 0.40, \
            f"Processing ratio {processing_ratio:.2%} outside target range (10-40%)"
    
    @pytest.mark.asyncio
    async def test_high_value_pages_identified(self, analyzer, classifier, duplicate_detector):
        """Test that high-value insurance pages are identified."""
        signals = await analyzer.analyze_document(HARBOR_COVE_PDF_URL)
        
        classifications = []
        for signal in signals:
            is_dup, dup_of = duplicate_detector.is_duplicate(signal)
            
            if is_dup:
                classification = PageClassification(
                    page_number=signal.page_number,
                    page_type=PageType.DUPLICATE,
                    confidence=1.0,
                    should_process=False,
                    duplicate_of=dup_of,
                    reasoning=f"Duplicate of page {dup_of}"
                )
            else:
                classification = classifier.classify(signal)
            
            classifications.append(classification)
        
        # Check that we identified key page types
        page_types = {c.page_type for c in classifications}
        
        # Should find at least some of these key types in an insurance document
        expected_types = {PageType.DECLARATIONS, PageType.COVERAGES, PageType.ENDORSEMENT}
        found_types = page_types.intersection(expected_types)
        
        assert len(found_types) > 0, \
            f"Expected to find insurance page types, found: {page_types}"
    
    @pytest.mark.asyncio
    async def test_duplicate_detection_works(self, analyzer, duplicate_detector):
        """Test that duplicate detection identifies repeated pages."""
        signals = await analyzer.analyze_document(HARBOR_COVE_PDF_URL)
        
        duplicate_count = 0
        for signal in signals:
            is_dup, dup_of = duplicate_detector.is_duplicate(signal)
            if is_dup:
                duplicate_count += 1
        
        # Insurance documents often have some duplicates (forms, clauses)
        # But not all pages should be duplicates
        assert duplicate_count < len(signals), "All pages detected as duplicates"
    
    @pytest.mark.asyncio
    async def test_classification_confidence(self, analyzer, classifier, duplicate_detector):
        """Test that classifications have reasonable confidence scores."""
        signals = await analyzer.analyze_document(HARBOR_COVE_PDF_URL)
        
        classifications = []
        for signal in signals:
            is_dup, dup_of = duplicate_detector.is_duplicate(signal)
            
            if not is_dup:
                classification = classifier.classify(signal)
                classifications.append(classification)
        
        # All classifications should have valid confidence scores
        for c in classifications:
            assert 0.0 <= c.confidence <= 1.0
        
        # At least some should have high confidence
        high_confidence = [c for c in classifications if c.confidence >= 0.7]
        assert len(high_confidence) > 0, "No high-confidence classifications found"
