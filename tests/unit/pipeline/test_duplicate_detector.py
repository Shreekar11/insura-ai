"""Unit tests for DuplicateDetector.

Tests MinHash-based duplicate detection for insurance document pages.
"""

import pytest
from app.services.pipeline.duplicate_detector import DuplicateDetector
from app.models.page_analysis_models import PageSignals


class TestDuplicateDetectorBasic:
    """Basic duplicate detection tests."""
    
    @pytest.fixture
    def detector(self):
        """Create detector instance with default settings."""
        return DuplicateDetector(similarity_threshold=0.8, num_perm=128)
    
    def _create_signals(
        self,
        page_number: int,
        top_lines: list,
        page_hash: str = "default"
    ) -> PageSignals:
        """Helper to create PageSignals for testing."""
        return PageSignals(
            page_number=page_number,
            top_lines=top_lines,
            text_density=0.5,
            has_tables=False,
            max_font_size=12.0,
            page_hash=page_hash
        )
    
    def test_first_page_is_never_duplicate(self, detector):
        """Test that the first page seen is never a duplicate."""
        signals = self._create_signals(
            page_number=1,
            top_lines=["DECLARATIONS PAGE", "Policy Number: ABC-123"]
        )
        
        is_dup, dup_of = detector.is_duplicate(signals)
        
        assert is_dup is False
        assert dup_of is None
    
    def test_identical_content_detected_as_duplicate(self, detector):
        """Test that identical content is detected as duplicate."""
        # First page
        signals1 = self._create_signals(
            page_number=1,
            top_lines=["ISO FORM CG 00 01", "This is standard form language"]
        )
        
        # Second page with identical content
        signals2 = self._create_signals(
            page_number=5,
            top_lines=["ISO FORM CG 00 01", "This is standard form language"]
        )
        
        # Process first page
        is_dup1, _ = detector.is_duplicate(signals1)
        assert is_dup1 is False
        
        # Process second page - should be duplicate
        is_dup2, dup_of = detector.is_duplicate(signals2)
        assert is_dup2 is True
        assert dup_of == 1
    
    def test_different_content_not_duplicate(self, detector):
        """Test that different content is not detected as duplicate."""
        signals1 = self._create_signals(
            page_number=1,
            top_lines=["DECLARATIONS PAGE", "Policy Number: ABC-123"]
        )
        
        signals2 = self._create_signals(
            page_number=2,
            top_lines=["COVERAGES", "Coverage A - Building", "Limit: $5,000,000"]
        )
        
        detector.is_duplicate(signals1)
        is_dup, dup_of = detector.is_duplicate(signals2)
        
        assert is_dup is False
        assert dup_of is None
    
    def test_similar_content_above_threshold_is_duplicate(self, detector):
        """Test that similar content above threshold is detected as duplicate."""
        # Original page
        signals1 = self._create_signals(
            page_number=1,
            top_lines=[
                "COMMERCIAL GENERAL LIABILITY FORM",
                "Coverage A - Bodily Injury and Property Damage",
                "We will pay those sums that the insured becomes legally obligated"
            ]
        )
        
        # Very similar page (minor differences)
        signals2 = self._create_signals(
            page_number=10,
            top_lines=[
                "COMMERCIAL GENERAL LIABILITY FORM",
                "Coverage A - Bodily Injury and Property Damage",
                "We will pay those sums that the insured becomes legally obligated to pay"
            ]
        )
        
        detector.is_duplicate(signals1)
        is_dup, _ = detector.is_duplicate(signals2)
        
        # Should be detected as duplicate due to high similarity
        assert is_dup is True
    
    def test_different_content_below_threshold_not_duplicate(self, detector):
        """Test that content below similarity threshold is not duplicate."""
        signals1 = self._create_signals(
            page_number=1,
            top_lines=["DECLARATIONS PAGE", "Named Insured: ABC Company"]
        )
        
        signals2 = self._create_signals(
            page_number=50,
            top_lines=["ENDORSEMENT NO. 1", "This endorsement changes the policy"]
        )
        
        detector.is_duplicate(signals1)
        is_dup, dup_of = detector.is_duplicate(signals2)
        
        assert is_dup is False
        assert dup_of is None


class TestDuplicateDetectorThreshold:
    """Test threshold behavior."""
    
    def test_high_threshold_reduces_duplicates(self):
        """Test that higher threshold reduces duplicate detection."""
        # Strict threshold
        strict_detector = DuplicateDetector(similarity_threshold=0.95)
        
        # Lenient threshold
        lenient_detector = DuplicateDetector(similarity_threshold=0.5)
        
        signals1 = PageSignals(
            page_number=1,
            top_lines=["ISO FORM CG 00 01", "Standard form language here"],
            text_density=0.5,
            has_tables=False,
            max_font_size=12.0,
            page_hash="hash1"
        )
        
        # Similar but not identical
        signals2 = PageSignals(
            page_number=5,
            top_lines=["ISO FORM CG 00 01", "Standard form language"],
            text_density=0.5,
            has_tables=False,
            max_font_size=12.0,
            page_hash="hash2"
        )
        
        # Process with strict detector
        strict_detector.is_duplicate(signals1)
        strict_is_dup, _ = strict_detector.is_duplicate(signals2)
        
        # Process with lenient detector
        lenient_detector.is_duplicate(signals1)
        lenient_is_dup, _ = lenient_detector.is_duplicate(signals2)
        
        # Lenient should detect more duplicates
        # (or at least not fewer)
        if strict_is_dup:
            assert lenient_is_dup is True
    
    def test_default_threshold_is_reasonable(self):
        """Test that default threshold (0.8) provides reasonable detection."""
        detector = DuplicateDetector()  # Uses default 0.8
        
        assert detector.similarity_threshold == 0.8


class TestDuplicateDetectorReset:
    """Test reset functionality."""
    
    def test_reset_clears_seen_pages(self):
        """Test that reset clears all seen pages."""
        detector = DuplicateDetector()
        
        # Add some pages
        signals1 = PageSignals(
            page_number=1,
            top_lines=["Page 1 content"],
            text_density=0.5,
            has_tables=False,
            max_font_size=12.0,
            page_hash="hash1"
        )
        
        signals2 = PageSignals(
            page_number=2,
            top_lines=["Page 2 content"],
            text_density=0.5,
            has_tables=False,
            max_font_size=12.0,
            page_hash="hash2"
        )
        
        detector.is_duplicate(signals1)
        detector.is_duplicate(signals2)
        
        assert len(detector.seen_pages) == 2
        
        # Reset
        detector.reset()
        
        assert len(detector.seen_pages) == 0
    
    def test_after_reset_no_duplicates_detected(self):
        """Test that after reset, previously seen pages are not duplicates."""
        detector = DuplicateDetector()
        
        signals = PageSignals(
            page_number=1,
            top_lines=["Identical content"],
            text_density=0.5,
            has_tables=False,
            max_font_size=12.0,
            page_hash="hash1"
        )
        
        # First pass
        detector.is_duplicate(signals)
        
        # Reset
        detector.reset()
        
        # Same content should not be duplicate after reset
        is_dup, _ = detector.is_duplicate(signals)
        assert is_dup is False


class TestDuplicateDetectorStats:
    """Test statistics functionality."""
    
    def test_get_stats_returns_correct_counts(self):
        """Test that get_stats returns accurate statistics."""
        detector = DuplicateDetector(similarity_threshold=0.8, num_perm=128)
        
        # Add some pages
        for i in range(5):
            signals = PageSignals(
                page_number=i + 1,
                top_lines=[f"Unique content for page {i}"],
                text_density=0.5,
                has_tables=False,
                max_font_size=12.0,
                page_hash=f"hash{i}"
            )
            detector.is_duplicate(signals)
        
        stats = detector.get_stats()
        
        assert stats["total_pages_seen"] == 5
        assert stats["similarity_threshold"] == 0.8
        assert stats["num_permutations"] == 128


class TestDuplicateDetectorEdgeCases:
    """Test edge cases."""
    
    @pytest.fixture
    def detector(self):
        """Create detector instance."""
        return DuplicateDetector()
    
    def test_empty_top_lines(self, detector):
        """Test handling of empty top lines."""
        signals1 = PageSignals(
            page_number=1,
            top_lines=[],
            text_density=0.1,
            has_tables=False,
            max_font_size=None,
            page_hash="empty1"
        )
        
        signals2 = PageSignals(
            page_number=2,
            top_lines=[],
            text_density=0.1,
            has_tables=False,
            max_font_size=None,
            page_hash="empty2"
        )
        
        # Should not crash
        detector.is_duplicate(signals1)
        is_dup, _ = detector.is_duplicate(signals2)
        
        # Empty pages might be considered duplicates
        # (depends on MinHash behavior with empty input)
        assert isinstance(is_dup, bool)
    
    def test_single_word_top_lines(self, detector):
        """Test handling of single word top lines."""
        signals1 = PageSignals(
            page_number=1,
            top_lines=["DECLARATIONS"],
            text_density=0.5,
            has_tables=False,
            max_font_size=12.0,
            page_hash="hash1"
        )
        
        signals2 = PageSignals(
            page_number=2,
            top_lines=["COVERAGES"],
            text_density=0.5,
            has_tables=False,
            max_font_size=12.0,
            page_hash="hash2"
        )
        
        detector.is_duplicate(signals1)
        is_dup, _ = detector.is_duplicate(signals2)
        
        # Single different words should not be duplicates
        assert is_dup is False
    
    def test_whitespace_normalization(self, detector):
        """Test that whitespace is normalized during comparison."""
        signals1 = PageSignals(
            page_number=1,
            top_lines=["DECLARATIONS   PAGE", "Policy   Number:  ABC"],
            text_density=0.5,
            has_tables=False,
            max_font_size=12.0,
            page_hash="hash1"
        )
        
        signals2 = PageSignals(
            page_number=2,
            top_lines=["DECLARATIONS PAGE", "Policy Number: ABC"],
            text_density=0.5,
            has_tables=False,
            max_font_size=12.0,
            page_hash="hash2"
        )
        
        detector.is_duplicate(signals1)
        is_dup, _ = detector.is_duplicate(signals2)
        
        # Should be detected as duplicate despite whitespace differences
        assert is_dup is True
    
    def test_case_insensitivity(self, detector):
        """Test that comparison is case-insensitive."""
        signals1 = PageSignals(
            page_number=1,
            top_lines=["DECLARATIONS PAGE", "POLICY NUMBER: ABC-123"],
            text_density=0.5,
            has_tables=False,
            max_font_size=12.0,
            page_hash="hash1"
        )
        
        signals2 = PageSignals(
            page_number=2,
            top_lines=["declarations page", "policy number: abc-123"],
            text_density=0.5,
            has_tables=False,
            max_font_size=12.0,
            page_hash="hash2"
        )
        
        detector.is_duplicate(signals1)
        is_dup, _ = detector.is_duplicate(signals2)
        
        # Should be detected as duplicate despite case differences
        assert is_dup is True


class TestDuplicateDetectorInsuranceScenarios:
    """Test real-world insurance document scenarios."""
    
    @pytest.fixture
    def detector(self):
        """Create detector instance."""
        return DuplicateDetector(similarity_threshold=0.8)
    
    def test_repeated_iso_forms(self, detector):
        """Test detection of repeated ISO forms."""
        # ISO form appearing on page 50
        iso_form_1 = PageSignals(
            page_number=50,
            top_lines=[
                "COMMERCIAL GENERAL LIABILITY CG 00 01 04 13",
                "THIS ENDORSEMENT CHANGES THE POLICY",
                "PLEASE READ IT CAREFULLY"
            ],
            text_density=0.6,
            has_tables=False,
            max_font_size=12.0,
            page_hash="iso1"
        )
        
        # Same ISO form appearing on page 75
        iso_form_2 = PageSignals(
            page_number=75,
            top_lines=[
                "COMMERCIAL GENERAL LIABILITY CG 00 01 04 13",
                "THIS ENDORSEMENT CHANGES THE POLICY",
                "PLEASE READ IT CAREFULLY"
            ],
            text_density=0.6,
            has_tables=False,
            max_font_size=12.0,
            page_hash="iso2"
        )
        
        detector.is_duplicate(iso_form_1)
        is_dup, dup_of = detector.is_duplicate(iso_form_2)
        
        assert is_dup is True
        assert dup_of == 50
    
    def test_different_endorsements_not_duplicates(self, detector):
        """Test that different endorsements are not duplicates."""
        endorsement_1 = PageSignals(
            page_number=60,
            top_lines=[
                "ENDORSEMENT NO. 1",
                "ADDITIONAL INSURED - OWNERS, LESSEES",
                "Effective Date: 01/01/2024"
            ],
            text_density=0.5,
            has_tables=False,
            max_font_size=12.0,
            page_hash="end1"
        )
        
        endorsement_2 = PageSignals(
            page_number=65,
            top_lines=[
                "ENDORSEMENT NO. 2",
                "WAIVER OF SUBROGATION",
                "Effective Date: 01/01/2024"
            ],
            text_density=0.5,
            has_tables=False,
            max_font_size=12.0,
            page_hash="end2"
        )
        
        detector.is_duplicate(endorsement_1)
        is_dup, _ = detector.is_duplicate(endorsement_2)
        
        assert is_dup is False
    
    def test_repeated_boilerplate_disclaimers(self, detector):
        """Test detection of repeated boilerplate disclaimers."""
        disclaimer_1 = PageSignals(
            page_number=100,
            top_lines=[
                "IMPORTANT NOTICE",
                "This policy contains important information about your coverage.",
                "Please read it carefully and keep it in a safe place."
            ],
            text_density=0.3,
            has_tables=False,
            max_font_size=10.0,
            page_hash="disc1"
        )
        
        disclaimer_2 = PageSignals(
            page_number=120,
            top_lines=[
                "IMPORTANT NOTICE",
                "This policy contains important information about your coverage.",
                "Please read it carefully and keep it in a safe place."
            ],
            text_density=0.3,
            has_tables=False,
            max_font_size=10.0,
            page_hash="disc2"
        )
        
        detector.is_duplicate(disclaimer_1)
        is_dup, dup_of = detector.is_duplicate(disclaimer_2)
        
        assert is_dup is True
        assert dup_of == 100

