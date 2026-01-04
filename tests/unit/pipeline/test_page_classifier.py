"""Unit tests for PageClassifier.

Tests rule-based page classification for insurance documents,
ensuring alignment with semantic anchors and page roles.
"""

import pytest
from app.services.page_analysis.page_classifier import PageClassifier
from app.models.page_analysis_models import PageSignals, PageClassification, PageType


class TestPageClassifierPatternMatching:
    """Test pattern matching for insurance document sections."""
    
    @pytest.fixture
    def classifier(self):
        """Create classifier instance with default threshold."""
        return PageClassifier(confidence_threshold=0.7)
    
    def _create_signals(
        self,
        page_number: int,
        top_lines: list,
        text_density: float = 0.5,
        has_tables: bool = False,
        max_font_size: float = 12.0,
        page_hash: str = "abc123"
    ) -> PageSignals:
        """Helper to create PageSignals for testing."""
        return PageSignals(
            page_number=page_number,
            top_lines=top_lines,
            text_density=text_density,
            has_tables=has_tables,
            max_font_size=max_font_size,
            page_hash=page_hash
        )
    
    # ========== DECLARATIONS SECTION TESTS ==========
    
    def test_classify_declarations_page_with_keyword(self, classifier):
        """Test classification of declarations page with explicit keyword."""
        signals = self._create_signals(
            page_number=1,
            top_lines=[
                "DECLARATIONS PAGE",
                "Policy Number: ABC-123456",
                "Named Insured: XYZ Manufacturing LLC"
            ],
            text_density=0.8,
            max_font_size=18.0
        )
        
        result = classifier.classify(signals)
        
        assert result.page_type == PageType.DECLARATIONS
        assert result.should_process is True
        assert result.confidence >= 0.7
    
    def test_classify_declarations_with_policy_period(self, classifier):
        """Test declarations detection via policy period keyword."""
        signals = self._create_signals(
            page_number=2,
            top_lines=[
                "COMMERCIAL PROPERTY POLICY",
                "Policy Period: 01/01/2024 to 01/01/2025",
                "Effective Date: January 1, 2024"
            ],
            text_density=0.75
        )
        
        result = classifier.classify(signals)
        
        assert result.page_type == PageType.DECLARATIONS
        assert result.should_process is True
    
    def test_classify_declarations_with_named_insured(self, classifier):
        """Test declarations detection via named insured keyword."""
        signals = self._create_signals(
            page_number=1,
            top_lines=[
                "PROPERTY INSURANCE POLICY",
                "Named Insured: Harbor Cove Properties Inc.",
                "Mailing Address: 123 Main Street"
            ]
        )
        
        result = classifier.classify(signals)
        
        assert result.page_type == PageType.DECLARATIONS
        assert result.should_process is True
    
    # ========== COVERAGES SECTION TESTS ==========
    
    def test_classify_coverages_page(self, classifier):
        """Test classification of coverages section."""
        signals = self._create_signals(
            page_number=10,
            top_lines=[
                "SECTION I - COVERAGES",
                "Coverage A - Building",
                "Limits of Insurance"
            ],
            text_density=0.7
        )
        
        result = classifier.classify(signals)
        
        assert result.page_type == PageType.COVERAGES
        assert result.should_process is True
    
    def test_classify_coverages_with_limits(self, classifier):
        """Test coverages detection via limits keyword."""
        signals = self._create_signals(
            page_number=15,
            top_lines=[
                "LIMITS AND DEDUCTIBLES",
                "Coverage Limit: $5,000,000",
                "Deductible: $10,000"
            ]
        )
        
        result = classifier.classify(signals)
        
        assert result.page_type == PageType.COVERAGES
        assert result.should_process is True
    
    def test_classify_insuring_agreement(self, classifier):
        """Test coverages detection via insuring agreement."""
        signals = self._create_signals(
            page_number=8,
            top_lines=[
                "INSURING AGREEMENT",
                "We will pay for direct physical loss of or damage to",
                "Covered Property at the premises described"
            ]
        )
        
        result = classifier.classify(signals)
        
        assert result.page_type == PageType.COVERAGES
        assert result.should_process is True
    
    # ========== CONDITIONS SECTION TESTS ==========
    
    def test_classify_conditions_page(self, classifier):
        """Test classification of conditions section."""
        signals = self._create_signals(
            page_number=25,
            top_lines=[
                "SECTION II - CONDITIONS",
                "General Conditions",
                "Your Duties After Loss"
            ]
        )
        
        result = classifier.classify(signals)
        
        assert result.page_type == PageType.CONDITIONS
        # Conditions should be processed if confidence is high
        assert result.confidence >= 0.5
    
    def test_classify_duties_in_event_of_loss(self, classifier):
        """Test conditions detection via duties keyword."""
        signals = self._create_signals(
            page_number=30,
            top_lines=[
                "DUTIES IN THE EVENT OF LOSS OR DAMAGE",
                "You must see that the following are done",
                "in the event of loss or damage"
            ]
        )
        
        result = classifier.classify(signals)
        
        assert result.page_type == PageType.CONDITIONS
    
    # ========== EXCLUSIONS SECTION TESTS ==========
    
    def test_classify_exclusions_page(self, classifier):
        """Test classification of exclusions section."""
        signals = self._create_signals(
            page_number=20,
            top_lines=[
                "EXCLUSIONS",
                "This insurance does not apply to:",
                "1. Earth Movement"
            ]
        )
        
        result = classifier.classify(signals)
        
        assert result.page_type == PageType.EXCLUSIONS
    
    def test_classify_what_is_not_covered(self, classifier):
        """Test exclusions detection via 'what is not covered'."""
        signals = self._create_signals(
            page_number=22,
            top_lines=[
                "WHAT IS NOT COVERED",
                "We do not cover loss or damage caused by",
                "any of the following:"
            ]
        )
        
        result = classifier.classify(signals)
        
        assert result.page_type == PageType.EXCLUSIONS
    
    # ========== ENDORSEMENT SECTION TESTS ==========
    
    def test_classify_endorsement_page(self, classifier):
        """Test classification of endorsement."""
        signals = self._create_signals(
            page_number=50,
            top_lines=[
                "ENDORSEMENT NO. 1",
                "This endorsement changes the policy.",
                "Please read it carefully."
            ]
        )
        
        result = classifier.classify(signals)
        
        assert result.page_type == PageType.ENDORSEMENT
        assert result.should_process is True  # Endorsements are key sections
    
    def test_classify_attached_endorsement(self, classifier):
        """Test endorsement detection via attached endorsement keyword."""
        signals = self._create_signals(
            page_number=55,
            top_lines=[
                "ATTACHED ENDORSEMENT",
                "This endorsement changes the policy",
                "Premium Change: $500"
            ]
        )
        
        result = classifier.classify(signals)
        
        assert result.page_type == PageType.ENDORSEMENT
        assert result.should_process is True
    
    # ========== SOV (SCHEDULE OF VALUES) TESTS ==========
    
    def test_classify_sov_page(self, classifier):
        """Test classification of Schedule of Values."""
        signals = self._create_signals(
            page_number=60,
            top_lines=[
                "SCHEDULE OF VALUES",
                "Location 1: 123 Main Street",
                "Building Limit: $10,000,000"
            ],
            has_tables=True
        )
        
        result = classifier.classify(signals)
        
        assert result.page_type == PageType.SOV
    
    def test_classify_location_schedule(self, classifier):
        """Test SOV detection via location schedule keyword."""
        signals = self._create_signals(
            page_number=65,
            top_lines=[
                "LOCATION SCHEDULE",
                "Loc #  Address  Building Value  Contents Value",
                "1      123 Main St  $5,000,000  $1,000,000"
            ],
            has_tables=True
        )
        
        result = classifier.classify(signals)
        
        assert result.page_type == PageType.SOV
    
    def test_classify_property_schedule(self, classifier):
        """Test SOV detection via property schedule keyword."""
        signals = self._create_signals(
            page_number=70,
            top_lines=[
                "PROPERTY SCHEDULE",
                "Building Schedule - All Locations"
            ],
            has_tables=True
        )
        
        result = classifier.classify(signals)
        
        assert result.page_type == PageType.SOV
    
    # ========== LOSS RUN TESTS ==========
    
    def test_classify_loss_run_page(self, classifier):
        """Test classification of Loss Run."""
        signals = self._create_signals(
            page_number=80,
            top_lines=[
                "LOSS RUN REPORT",
                "Policy Period: 2020-2024",
                "Total Incurred: $150,000"
            ],
            has_tables=True
        )
        
        result = classifier.classify(signals)
        
        assert result.page_type == PageType.LOSS_RUN
    
    def test_classify_claims_history(self, classifier):
        """Test loss run detection via claims history keyword."""
        signals = self._create_signals(
            page_number=85,
            top_lines=[
                "CLAIMS HISTORY",
                "Claim Number  Date of Loss  Status  Paid",
                "CLM-001  01/15/2023  Closed  $25,000"
            ],
            has_tables=True
        )
        
        result = classifier.classify(signals)
        
        assert result.page_type == PageType.LOSS_RUN
    
    # ========== BOILERPLATE TESTS ==========
    
    def test_classify_boilerplate_iso_page(self, classifier):
        """Test classification of ISO boilerplate."""
        signals = self._create_signals(
            page_number=100,
            top_lines=[
                "ISO PROPERTIES, INC., 2017",
                "Includes copyrighted material of Insurance",
                "Services Office, Inc."
            ],
            text_density=0.3
        )
        
        result = classifier.classify(signals)
        
        assert result.page_type == PageType.BOILERPLATE
        assert result.should_process is False  # Boilerplate should be skipped
    
    def test_classify_copyright_boilerplate(self, classifier):
        """Test boilerplate detection via copyright keyword."""
        signals = self._create_signals(
            page_number=105,
            top_lines=[
                "COPYRIGHT ISO 2018",
                "This form is copyrighted material",
                "Page 1 of 50"
            ],
            text_density=0.2
        )
        
        result = classifier.classify(signals)
        
        assert result.page_type == PageType.BOILERPLATE
        assert result.should_process is False
    
    # ========== UNKNOWN / LOW CONFIDENCE TESTS ==========
    
    def test_classify_unknown_page(self, classifier):
        """Test classification of page with no matching patterns."""
        signals = self._create_signals(
            page_number=40,
            top_lines=[
                "Some random text here",
                "That doesn't match any patterns",
                "Just general content"
            ],
            text_density=0.5
        )
        
        result = classifier.classify(signals)
        
        assert result.page_type == PageType.UNKNOWN
        # Unknown pages are skipped by default for aggressive filtering
        assert result.should_process is False
    
    def test_classify_empty_top_lines(self, classifier):
        """Test classification with empty top lines."""
        signals = self._create_signals(
            page_number=90,
            top_lines=[],
            text_density=0.1
        )
        
        result = classifier.classify(signals)
        
        assert result.page_type == PageType.UNKNOWN
        assert result.confidence < 0.5


class TestPageClassifierHeuristics:
    """Test structural heuristics applied during classification."""
    
    @pytest.fixture
    def classifier(self):
        """Create classifier instance."""
        return PageClassifier(confidence_threshold=0.7)
    
    def _create_signals(
        self,
        page_number: int,
        top_lines: list,
        text_density: float = 0.5,
        has_tables: bool = False,
        max_font_size: float = 12.0,
        page_hash: str = "abc123"
    ) -> PageSignals:
        """Helper to create PageSignals."""
        return PageSignals(
            page_number=page_number,
            top_lines=top_lines,
            text_density=text_density,
            has_tables=has_tables,
            max_font_size=max_font_size,
            page_hash=page_hash
        )
    
    def test_early_page_confidence_boost(self, classifier):
        """Test that early pages (1-5) get confidence boost."""
        # Same content, different page numbers
        early_signals = self._create_signals(
            page_number=2,
            top_lines=["POLICY INFORMATION"],
            text_density=0.6
        )
        
        late_signals = self._create_signals(
            page_number=50,
            top_lines=["POLICY INFORMATION"],
            text_density=0.6
        )
        
        early_result = classifier.classify(early_signals)
        late_result = classifier.classify(late_signals)
        
        # Early page should have higher confidence due to heuristic boost
        assert early_result.confidence > late_result.confidence
    
    def test_high_text_density_confidence_boost(self, classifier):
        """Test that high text density boosts confidence."""
        high_density = self._create_signals(
            page_number=10,
            top_lines=["COVERAGE DETAILS"],
            text_density=0.85
        )
        
        low_density = self._create_signals(
            page_number=10,
            top_lines=["COVERAGE DETAILS"],
            text_density=0.3
        )
        
        high_result = classifier.classify(high_density)
        low_result = classifier.classify(low_density)
        
        assert high_result.confidence > low_result.confidence
    
    def test_large_font_confidence_boost(self, classifier):
        """Test that large font sizes boost confidence."""
        large_font = self._create_signals(
            page_number=10,
            top_lines=["DECLARATIONS"],
            max_font_size=24.0
        )
        
        small_font = self._create_signals(
            page_number=10,
            top_lines=["DECLARATIONS"],
            max_font_size=10.0
        )
        
        large_result = classifier.classify(large_font)
        small_result = classifier.classify(small_font)
        
        assert large_result.confidence > small_result.confidence
    
    def test_tables_boost_sov_confidence(self, classifier):
        """Test that tables boost SOV classification confidence."""
        with_tables = self._create_signals(
            page_number=60,
            top_lines=["SCHEDULE OF VALUES"],
            has_tables=True
        )
        
        without_tables = self._create_signals(
            page_number=60,
            top_lines=["SCHEDULE OF VALUES"],
            has_tables=False
        )
        
        with_result = classifier.classify(with_tables)
        without_result = classifier.classify(without_tables)
        
        assert with_result.confidence > without_result.confidence
    
    def test_tables_boost_loss_run_confidence(self, classifier):
        """Test that tables boost Loss Run classification confidence."""
        with_tables = self._create_signals(
            page_number=80,
            top_lines=["LOSS RUN REPORT"],
            has_tables=True
        )
        
        without_tables = self._create_signals(
            page_number=80,
            top_lines=["LOSS RUN REPORT"],
            has_tables=False
        )
        
        with_result = classifier.classify(with_tables)
        without_result = classifier.classify(without_tables)
        
        assert with_result.confidence > without_result.confidence


class TestPageClassifierProcessingDecisions:
    """Test should_process decision logic."""
    
    @pytest.fixture
    def classifier(self):
        """Create classifier instance."""
        return PageClassifier(confidence_threshold=0.7)
    
    def _create_signals(
        self,
        page_number: int,
        top_lines: list,
        text_density: float = 0.5,
        has_tables: bool = False,
        max_font_size: float = 12.0,
        page_hash: str = "abc123"
    ) -> PageSignals:
        """Helper to create PageSignals."""
        return PageSignals(
            page_number=page_number,
            top_lines=top_lines,
            text_density=text_density,
            has_tables=has_tables,
            max_font_size=max_font_size,
            page_hash=page_hash
        )
    
    def test_key_sections_always_processed(self, classifier):
        """Test that key sections (declarations, coverages, endorsements) are always processed."""
        # Declarations
        decl_signals = self._create_signals(
            page_number=1,
            top_lines=["DECLARATIONS PAGE"]
        )
        decl_result = classifier.classify(decl_signals)
        assert decl_result.should_process is True
        
        # Coverages
        cov_signals = self._create_signals(
            page_number=10,
            top_lines=["COVERAGES"]
        )
        cov_result = classifier.classify(cov_signals)
        assert cov_result.should_process is True
        
        # Endorsements
        end_signals = self._create_signals(
            page_number=50,
            top_lines=["ENDORSEMENT NO. 1"]
        )
        end_result = classifier.classify(end_signals)
        assert end_result.should_process is True
    
    def test_boilerplate_never_processed(self, classifier):
        """Test that boilerplate pages are never processed."""
        signals = self._create_signals(
            page_number=100,
            top_lines=["ISO PROPERTIES, INC., 2017", "COPYRIGHT ISO"]
        )
        
        result = classifier.classify(signals)
        
        assert result.page_type == PageType.BOILERPLATE
        assert result.should_process is False
    
    def test_unknown_pages_skipped_by_default(self, classifier):
        """Test that unknown pages are skipped (aggressive filtering)."""
        signals = self._create_signals(
            page_number=40,
            top_lines=["Random content without keywords"]
        )
        
        result = classifier.classify(signals)
        
        assert result.page_type == PageType.UNKNOWN
        # Unknown pages are skipped by default for aggressive filtering
        assert result.should_process is False


class TestPageClassifierReasoning:
    """Test human-readable reasoning generation."""
    
    @pytest.fixture
    def classifier(self):
        """Create classifier instance."""
        return PageClassifier()
    
    def _create_signals(
        self,
        page_number: int,
        top_lines: list,
        text_density: float = 0.5,
        has_tables: bool = False,
        max_font_size: float = 12.0,
        page_hash: str = "abc123"
    ) -> PageSignals:
        """Helper to create PageSignals."""
        return PageSignals(
            page_number=page_number,
            top_lines=top_lines,
            text_density=text_density,
            has_tables=has_tables,
            max_font_size=max_font_size,
            page_hash=page_hash
        )
    
    def test_reasoning_includes_keyword_match(self, classifier):
        """Test that reasoning mentions keyword matches."""
        signals = self._create_signals(
            page_number=1,
            top_lines=["DECLARATIONS PAGE"]
        )
        
        result = classifier.classify(signals)
        
        assert result.reasoning is not None
        assert "declarations" in result.reasoning.lower() or "keyword" in result.reasoning.lower()
    
    def test_reasoning_includes_early_page(self, classifier):
        """Test that reasoning mentions early page status."""
        signals = self._create_signals(
            page_number=2,
            top_lines=["Some content"]
        )
        
        result = classifier.classify(signals)
        
        assert "early page" in result.reasoning.lower()
    
    def test_reasoning_includes_tables(self, classifier):
        """Test that reasoning mentions table presence."""
        signals = self._create_signals(
            page_number=60,
            top_lines=["SCHEDULE OF VALUES"],
            has_tables=True
        )
        
        result = classifier.classify(signals)
        
        assert "table" in result.reasoning.lower()
    
    def test_reasoning_includes_text_density(self, classifier):
        """Test that reasoning mentions text density."""
        signals = self._create_signals(
            page_number=10,
            top_lines=["COVERAGE DETAILS"],
            text_density=0.9
        )
        
        result = classifier.classify(signals)
        
        assert "density" in result.reasoning.lower()


class TestPageClassifierConfidenceThreshold:
    """Test confidence threshold behavior."""
    
    def test_custom_threshold_affects_processing(self):
        """Test that custom threshold affects processing decisions."""
        # Low threshold classifier
        low_threshold = PageClassifier(confidence_threshold=0.3)
        
        # High threshold classifier
        high_threshold = PageClassifier(confidence_threshold=0.9)
        
        signals = PageSignals(
            page_number=40,
            top_lines=["INVOICE", "Amount Due: $5,000"],
            text_density=0.5,
            has_tables=False,
            max_font_size=12.0,
            page_hash="test123"
        )
        
        low_result = low_threshold.classify(signals)
        high_result = high_threshold.classify(signals)
        
        # Both should classify the same type
        assert low_result.page_type == high_result.page_type
        
        # But processing decision may differ based on confidence threshold
        # (This depends on the actual confidence score)

