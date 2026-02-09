"""Tests for endorsement continuation detection.

IMPORTANT: Based on real document analysis (POL_CA_T4_52_02_16.pdf), these tests
use CONTENT-BASED signals rather than form numbers, which are unreliable.

Key signals tested:
- Mid-sentence start detection
- Alphabetic section sequence (A, B, C -> D, E, F)
- Explicit continuation text
- Endorsement context window
"""

import pytest
from app.models.page_analysis_models import (
    PageSignals,
    PageType,
    DocumentType,
    SemanticRole,
)
from app.services.processed.services.analysis.page_classifier import PageClassifier
from app.services.processed.services.analysis.endorsement_tracker import (
    EndorsementTracker,
    EndorsementContext,
    is_sequence_continuation,
)
from app.services.processed.services.analysis.markdown_page_analyzer import MarkdownPageAnalyzer


class TestIsSequenceContinuation:
    """Test the section sequence continuation helper function."""

    def test_alphabetic_sequence_continuation(self):
        """Test A, B, C -> D, E, F is detected as continuation."""
        is_cont, reason = is_sequence_continuation(["A", "B", "C"], ["D", "E", "F"])
        assert is_cont is True
        assert "C -> D" in reason

    def test_alphabetic_non_continuation(self):
        """Test A, B, C -> A, B is NOT a continuation."""
        is_cont, _ = is_sequence_continuation(["A", "B", "C"], ["A", "B"])
        assert is_cont is False

    def test_numeric_sequence_continuation(self):
        """Test 1, 2, 3 -> 4, 5 is detected as continuation."""
        is_cont, reason = is_sequence_continuation(["1", "2", "3"], ["4", "5"])
        assert is_cont is True
        assert "3 -> 4" in reason

    def test_empty_labels(self):
        """Test empty labels don't cause errors."""
        is_cont, _ = is_sequence_continuation([], ["A"])
        assert is_cont is False

        is_cont, _ = is_sequence_continuation(["A"], [])
        assert is_cont is False


class TestEndorsementTracker:
    """Tests for EndorsementTracker with content-based signals."""

    @pytest.fixture
    def tracker(self):
        return EndorsementTracker()

    def test_mid_sentence_continuation_detection(self, tracker):
        """Test continuation detection via mid-sentence start - MOST RELIABLE SIGNAL."""
        # Start endorsement on page 5
        page5_signals = PageSignals(
            page_number=5,
            top_lines=["THIS ENDORSEMENT CHANGES THE POLICY", "BUSINESS AUTO EXTENSION"],
            all_lines=["THIS ENDORSEMENT CHANGES THE POLICY", "..."],
            text_density=0.8,
            has_tables=False,
            page_hash="hash5",
            has_endorsement_header=True,
            section_labels=["A", "B", "C"],
            last_section_label="C",
        )
        tracker.start_endorsement(page5_signals)

        # Page 6 starts mid-sentence (lowercase "permission,")
        page6_signals = PageSignals(
            page_number=6,
            top_lines=["permission, while performing duties"],
            all_lines=["permission, while performing duties...", "D. EMPLOYEES AS INSURED"],
            text_density=0.8,
            has_tables=False,
            page_hash="hash6",
            has_endorsement_header=False,
            starts_mid_sentence=True,
            first_line_text="permission, while performing duties related to the conduct of your business.",
            section_labels=["D", "E", "F"],
        )

        is_cont, ctx, conf, reason = tracker.check_continuation(page6_signals)

        assert is_cont is True
        assert conf >= 0.80  # Mid-sentence gives 0.85 confidence
        assert "Mid-sentence" in reason

    def test_section_sequence_continuation(self, tracker):
        """Test continuation detection via alphabetic section sequence."""
        # Start endorsement with sections A, B, C
        page5_signals = PageSignals(
            page_number=5,
            top_lines=["THIS ENDORSEMENT CHANGES THE POLICY"],
            all_lines=["..."],
            text_density=0.8,
            has_tables=False,
            page_hash="hash5",
            has_endorsement_header=True,
            section_labels=["A", "B", "C"],
            last_section_label="C",
        )
        tracker.start_endorsement(page5_signals)

        # Page 6 continues with D, E, F
        page6_signals = PageSignals(
            page_number=6,
            top_lines=["D. EMPLOYEES AS INSURED"],
            all_lines=["D. EMPLOYEES AS INSURED", "E. SUPPLEMENTARY PAYMENTS"],
            text_density=0.8,
            has_tables=False,
            page_hash="hash6",
            has_endorsement_header=False,
            section_labels=["D", "E", "F"],
            starts_mid_sentence=False,
        )

        is_cont, ctx, conf, reason = tracker.check_continuation(page6_signals)

        assert is_cont is True
        assert "Section sequence: C -> D" in reason

    def test_explicit_continuation_text(self, tracker):
        """Test continuation detection via explicit CONTINUATION text."""
        # Start endorsement
        page10_signals = PageSignals(
            page_number=10,
            top_lines=["THIS ENDORSEMENT CHANGES THE POLICY"],
            all_lines=["..."],
            text_density=0.8,
            has_tables=False,
            page_hash="hash10",
            has_endorsement_header=True,
        )
        tracker.start_endorsement(page10_signals)

        # Page 11 has explicit "CONTINUATION OF FORM"
        page11_signals = PageSignals(
            page_number=11,
            top_lines=["CONTINUATION OF FORM IL T4 05"],
            all_lines=["CONTINUATION OF FORM IL T4 05", "..."],
            text_density=0.8,
            has_tables=False,
            page_hash="hash11",
            has_endorsement_header=False,
            explicit_continuation="CONTINUATION OF FORM IL T4 05",
        )

        is_cont, ctx, conf, reason = tracker.check_continuation(page11_signals)

        assert is_cont is True
        assert conf >= 0.90
        assert "Explicit continuation" in reason

    def test_new_endorsement_header_breaks_continuation(self, tracker):
        """Test that new endorsement header WITHOUT continuation text breaks the chain."""
        # Start endorsement
        tracker.start_endorsement(PageSignals(
            page_number=2,
            top_lines=["THIS ENDORSEMENT CHANGES THE POLICY"],
            all_lines=["..."],
            text_density=0.8,
            has_tables=False,
            page_hash="hash2",
            has_endorsement_header=True,
        ))

        # New endorsement with header (not a continuation)
        page4_signals = PageSignals(
            page_number=4,
            top_lines=["THIS ENDORSEMENT CHANGES THE POLICY"],
            all_lines=["THIS ENDORSEMENT CHANGES THE POLICY", "DIFFERENT ENDORSEMENT"],
            text_density=0.8,
            has_tables=False,
            page_hash="hash4",
            has_endorsement_header=True,
            explicit_continuation=None,
            starts_mid_sentence=False,
        )

        is_cont, _, _, reason = tracker.check_continuation(page4_signals)

        assert is_cont is False
        assert "New endorsement header" in reason

    def test_tracker_reset(self, tracker):
        """Test that reset clears active context."""
        tracker.start_endorsement(PageSignals(
            page_number=1,
            top_lines=["TEST"],
            all_lines=["TEST"],
            text_density=0.8,
            has_tables=False,
            page_hash="hash1",
            has_endorsement_header=True,
        ))

        assert tracker.active_context is not None
        tracker.reset()
        assert tracker.active_context is None


class TestMarkdownPageAnalyzerContinuation:
    """Tests for continuation signal extraction in MarkdownPageAnalyzer."""

    @pytest.fixture
    def analyzer(self):
        return MarkdownPageAnalyzer()

    def test_mid_sentence_detection_lowercase_start(self, analyzer):
        """Test mid-sentence detection when page starts with lowercase."""
        content = """permission, while performing duties related to the conduct of your business.

D. EMPLOYEES AS INSURED
"""
        signals = analyzer.analyze_markdown(content, page_number=6)

        assert signals.starts_mid_sentence is True
        assert signals.first_line_text is not None
        assert signals.first_line_text.startswith("permission")

    def test_section_label_extraction(self, analyzer):
        """Test extraction of section labels A, B, C, etc."""
        content = """## A. BROAD FORM NAMED INSURED
Some text here.

## B. BLANKET ADDITIONAL INSURED
More text.

## C. EMPLOYEE HIRED AUTO
Even more text.
"""
        signals = analyzer.analyze_markdown(content, page_number=5)

        assert "A" in signals.section_labels
        assert "B" in signals.section_labels
        assert "C" in signals.section_labels
        assert signals.last_section_label == "C"

    def test_endorsement_header_detection(self, analyzer):
        """Test detection of endorsement header patterns."""
        content = """# BUSINESS AUTO EXTENSION ENDORSEMENT

THIS ENDORSEMENT CHANGES THE POLICY. PLEASE READ IT CAREFULLY.

This endorsement modifies insurance provided under...
"""
        signals = analyzer.analyze_markdown(content, page_number=2)

        assert signals.has_endorsement_header is True

    def test_policy_number_extraction(self, analyzer):
        """Test extraction of policy number."""
        content = """BUSINESS AUTO EXTENSION ENDORSEMENT

Policy Number: BA-9M627065
Effective Date: 01/01/2024
"""
        signals = analyzer.analyze_markdown(content, page_number=3)

        assert signals.policy_number is not None
        assert "BA" in signals.policy_number or "9M627065" in signals.policy_number

    def test_explicit_continuation_detection(self, analyzer):
        """Test detection of explicit continuation text."""
        content = """(CONTINUED ON IL T8 03)

Additional terms and conditions apply.
"""
        signals = analyzer.analyze_markdown(content, page_number=10)

        assert signals.explicit_continuation is not None
        assert "CONTINUED" in signals.explicit_continuation.upper()


class TestPageClassifierBatch:
    """Tests for batch classification with continuation awareness."""

    @pytest.fixture
    def classifier(self):
        return PageClassifier.get_instance()

    def test_batch_classification_detects_continuations(self, classifier):
        """Test that batch classification properly detects endorsement continuations."""
        signals_list = [
            PageSignals(
                page_number=5,
                top_lines=["THIS ENDORSEMENT CHANGES THE POLICY", "BUSINESS AUTO EXTENSION"],
                all_lines=["THIS ENDORSEMENT CHANGES THE POLICY", "A. BROAD FORM NAMED INSURED"],
                text_density=0.8,
                has_tables=False,
                page_hash="hash5",
                has_endorsement_header=True,
                section_labels=["A", "B", "C"],
                last_section_label="C",
            ),
            PageSignals(
                page_number=6,
                top_lines=["permission, while performing duties"],
                all_lines=["permission, while performing duties", "D. EMPLOYEES AS INSURED"],
                text_density=0.8,
                has_tables=False,
                page_hash="hash6",
                has_endorsement_header=False,
                starts_mid_sentence=True,
                first_line_text="permission, while performing duties related.",
                section_labels=["D", "E", "F"],
            ),
        ]

        classifications = classifier.classify_batch(
            signals_list, doc_type=DocumentType.POLICY_BUNDLE
        )

        assert classifications[0].page_type == PageType.ENDORSEMENT
        assert classifications[1].page_type == PageType.ENDORSEMENT
        assert classifications[1].is_continuation is True
        assert classifications[1].should_process is True  # CRITICAL: Must not be skipped

    def test_batch_classification_strips_semantic_for_base_policy(self, classifier):
        """Test that semantic roles are stripped for base POLICY documents."""
        signals_list = [
            PageSignals(
                page_number=1,
                top_lines=["SECTION II - LIABILITY COVERAGE"],
                all_lines=["SECTION II - LIABILITY COVERAGE", "We will pay..."],
                text_density=0.8,
                has_tables=False,
                page_hash="hash1",
            ),
        ]

        classifications = classifier.classify_batch(
            signals_list, doc_type=DocumentType.POLICY
        )

        # For base policy, semantic roles should be stripped (unless it's an endorsement)
        if classifications[0].page_type != PageType.ENDORSEMENT:
            assert classifications[0].semantic_role is None or \
                   classifications[0].semantic_role == SemanticRole.UNKNOWN

    def test_certificate_gets_informational_only_role(self, classifier):
        """Test that certificates get INFORMATIONAL_ONLY semantic role."""
        signals_list = [
            PageSignals(
                page_number=1,
                top_lines=["CERTIFICATE OF INSURANCE"],
                all_lines=["CERTIFICATE OF INSURANCE", "This certificate is issued..."],
                text_density=0.8,
                has_tables=False,
                page_hash="hash1",
            ),
        ]

        classifications = classifier.classify_batch(
            signals_list, doc_type=DocumentType.POLICY_BUNDLE
        )

        assert classifications[0].page_type == PageType.CERTIFICATE_OF_INSURANCE
        assert classifications[0].semantic_role == SemanticRole.INFORMATIONAL_ONLY


class TestSubContentPromotion:
    """Tests for preventing sub-content promotion within endorsements."""

    @pytest.fixture
    def classifier(self):
        return PageClassifier.get_instance()

    def test_definitions_within_endorsement_not_promoted(self, classifier):
        """Test that definitions within endorsements are NOT promoted to top-level."""
        # Page with definition-like content but is a continuation
        signals_list = [
            PageSignals(
                page_number=2,
                top_lines=["THIS ENDORSEMENT CHANGES THE POLICY"],
                all_lines=["THIS ENDORSEMENT CHANGES THE POLICY", "A. Some provision"],
                text_density=0.8,
                has_tables=False,
                page_hash="hash2",
                has_endorsement_header=True,
                section_labels=["A", "B"],
                last_section_label="B",
            ),
            PageSignals(
                page_number=3,
                top_lines=["C. Additional Definition"],
                all_lines=[
                    "C. Additional Definition",
                    "As used in this endorsement:",
                    '"Leased auto" means...',
                ],
                text_density=0.8,
                has_tables=False,
                page_hash="hash3",
                has_endorsement_header=False,
                section_labels=["C", "D"],
                starts_mid_sentence=False,
            ),
        ]

        classifications = classifier.classify_batch(
            signals_list, doc_type=DocumentType.POLICY_BUNDLE
        )

        # Page 3 should be classified as endorsement (continuation), NOT definitions
        assert classifications[1].page_type == PageType.ENDORSEMENT
        assert classifications[1].is_continuation is True
        # Should NOT have been promoted to definitions
        for section in classifications[1].sections:
            assert section.section_type == PageType.ENDORSEMENT


class TestACORDCertificateOverride:
    """Tests for ACORD certificate hard override classification."""

    @pytest.fixture
    def classifier(self):
        return PageClassifier.get_instance()

    def test_acord_certificate_hard_override(self, classifier):
        """Test that ACORD certificates are detected with hard override."""
        signals = PageSignals(
            page_number=1,
            top_lines=[
                "CERTIFICATE OF LIABILITY INSURANCE",
                "DATE (MM/DD/YYYY)",
                "12/15/2020"
            ],
            all_lines=[
                "CERTIFICATE OF LIABILITY INSURANCE",
                "DATE (MM/DD/YYYY)",
                "THIS CERTIFICATE IS ISSUED AS A MATTER OF INFORMATION",
                "ONLY AND CONFERS NO RIGHTS UPON THE CERTIFICATE HOLDER.",
                "PRODUCER",
                "INSURED",
            ],
            text_density=0.8,
            has_tables=True,
            page_hash="hash1",
        )

        classification = classifier.classify(signals, DocumentType.POLICY_BUNDLE)

        assert classification.page_type == PageType.CERTIFICATE_OF_INSURANCE
        assert classification.confidence >= 0.98
        assert classification.semantic_role == SemanticRole.INFORMATIONAL_ONLY
        assert classification.should_process is False
        assert classification.coverage_effects == []
        assert classification.exclusion_effects == []

    def test_acord_25_detection(self, classifier):
        """Test detection of ACORD 25 form."""
        signals = PageSignals(
            page_number=1,
            top_lines=["ACORD 25 (2016/03)"],
            all_lines=["ACORD 25 (2016/03)", "CERTIFICATE OF LIABILITY INSURANCE"],
            text_density=0.7,
            has_tables=True,
            page_hash="hash1",
        )

        classification = classifier.classify(signals, DocumentType.POLICY_BUNDLE)

        assert classification.page_type == PageType.CERTIFICATE_OF_INSURANCE
        assert classification.should_process is False

    def test_certificate_not_mistaken_for_conditions(self, classifier):
        """Test that certificates with conditions-like content are still classified as certificates."""
        # This is the actual problem case - page 1 was being classified as "conditions"
        signals = PageSignals(
            page_number=1,
            top_lines=[
                "COVERAGES",
                "CERTIFICATE NUMBER: 1469263937"
            ],
            all_lines=[
                "COVERAGES",
                "CERTIFICATE NUMBER: 1469263937",
                "THIS CERTIFICATE IS ISSUED AS A MATTER OF INFORMATION",
                "ONLY AND CONFERS NO RIGHTS UPON THE CERTIFICATE HOLDER.",
                "INSURER(S) AFFORDING COVERAGE",
                "INSURED",
            ],
            text_density=0.8,
            has_tables=True,
            page_hash="hash1",
        )

        classification = classifier.classify(signals, DocumentType.POLICY_BUNDLE)

        # Should be certificate, NOT conditions
        assert classification.page_type == PageType.CERTIFICATE_OF_INSURANCE
        assert classification.semantic_role == SemanticRole.INFORMATIONAL_ONLY


class TestEndorsementHeaderOverride:
    """Tests for endorsement header hard override classification."""

    @pytest.fixture
    def classifier(self):
        return PageClassifier.get_instance()

    def test_endorsement_header_hard_override(self, classifier):
        """Test that endorsement header triggers hard override."""
        signals = PageSignals(
            page_number=2,
            top_lines=[
                "THIS ENDORSEMENT CHANGES THE POLICY. PLEASE READ IT CAREFULLY.",
                "BUSINESS AUTO EXTENSION ENDORSEMENT"
            ],
            all_lines=[
                "THIS ENDORSEMENT CHANGES THE POLICY. PLEASE READ IT CAREFULLY.",
                "BUSINESS AUTO EXTENSION ENDORSEMENT",
                "This endorsement modifies insurance provided under the following:",
                "BUSINESS AUTO COVERAGE FORM",
            ],
            text_density=0.8,
            has_tables=False,
            page_hash="hash2",
            has_endorsement_header=True,
        )

        classification = classifier.classify(signals, DocumentType.POLICY_BUNDLE)

        assert classification.page_type == PageType.ENDORSEMENT
        assert classification.confidence >= 0.95
        assert classification.should_process is True

    def test_endorsement_header_overrides_conditions(self, classifier):
        """Test that endorsement header overrides conditions-like content."""
        # This tests the regression where pages 9, 10, 11 were misclassified as conditions
        signals = PageSignals(
            page_number=9,
            top_lines=[
                "THIS ENDORSEMENT CHANGES THE POLICY. PLEASE READ IT CAREFULLY.",
                "DESIGNATED ENTITY - NOTICE OF CANCELLATION PROVIDED BY US"
            ],
            all_lines=[
                "THIS ENDORSEMENT CHANGES THE POLICY. PLEASE READ IT CAREFULLY.",
                "DESIGNATED ENTITY - NOTICE OF CANCELLATION PROVIDED BY US",
                "This endorsement modifies insurance provided under the following:",
                "ALL COVERAGE PARTS INCLUDED IN THIS POLICY",
                "SCHEDULE",
                "Number of Days Notice of Cancellation:",
            ],
            text_density=0.7,
            has_tables=False,
            page_hash="hash9",
            has_endorsement_header=True,
        )

        classification = classifier.classify(signals, DocumentType.POLICY_BUNDLE)

        # Should be endorsement, NOT conditions
        assert classification.page_type == PageType.ENDORSEMENT


class TestFormNumberContinuation:
    """Tests for form number-based endorsement continuation detection."""

    @pytest.fixture
    def tracker(self):
        return EndorsementTracker()

    def test_form_number_continuation_highest_priority(self, tracker):
        """Test that matching form numbers give highest confidence continuation."""
        # Start endorsement with form number
        page5_signals = PageSignals(
            page_number=5,
            top_lines=["THIS ENDORSEMENT CHANGES THE POLICY"],
            all_lines=["THIS ENDORSEMENT CHANGES THE POLICY", "BUSINESS AUTO EXTENSION"],
            text_density=0.8,
            has_tables=False,
            page_hash="hash5",
            has_endorsement_header=True,
            form_number="CA T3 53 02 15",  # From footer extraction
        )
        tracker.start_endorsement(page5_signals)

        # Page 6 has same form number - should be definite continuation
        page6_signals = PageSignals(
            page_number=6,
            top_lines=["D. EMPLOYEES AS INSURED"],
            all_lines=["D. EMPLOYEES AS INSURED", "Any employee of yours..."],
            text_density=0.8,
            has_tables=False,
            page_hash="hash6",
            has_endorsement_header=False,
            form_number="CA T3 53 02 15",  # Same form number
        )

        is_cont, ctx, conf, reason = tracker.check_continuation(page6_signals)

        assert is_cont is True
        assert conf >= 0.95  # Form number match gives highest confidence
        assert "Same form number" in reason

    def test_form_number_stored_in_context(self, tracker):
        """Test that form number is properly stored in endorsement context."""
        signals = PageSignals(
            page_number=2,
            top_lines=["THIS ENDORSEMENT CHANGES THE POLICY"],
            all_lines=["THIS ENDORSEMENT CHANGES THE POLICY"],
            text_density=0.8,
            has_tables=False,
            page_hash="hash2",
            has_endorsement_header=True,
            form_number="CA T4 52 02 16",
        )

        ctx = tracker.start_endorsement(signals)

        assert ctx.form_number == "CA T4 52 02 16"
        assert ctx.endorsement_id == "CA T4 52 02 16"

    def test_form_number_mismatch_not_continuation(self, tracker):
        """Test that different form numbers are NOT continuation."""
        # Start endorsement with form number
        page2_signals = PageSignals(
            page_number=2,
            top_lines=["THIS ENDORSEMENT CHANGES THE POLICY"],
            all_lines=["THIS ENDORSEMENT CHANGES THE POLICY"],
            text_density=0.8,
            has_tables=False,
            page_hash="hash2",
            has_endorsement_header=True,
            form_number="CA T4 52 02 16",
        )
        tracker.start_endorsement(page2_signals)

        # Page 4 has DIFFERENT form number - should NOT be continuation
        page4_signals = PageSignals(
            page_number=4,
            top_lines=["THIS ENDORSEMENT CHANGES THE POLICY"],
            all_lines=["THIS ENDORSEMENT CHANGES THE POLICY"],
            text_density=0.8,
            has_tables=False,
            page_hash="hash4",
            has_endorsement_header=True,
            form_number="CA T4 74 02 16",  # Different form number
        )

        is_cont, ctx, conf, reason = tracker.check_continuation(page4_signals)

        # Different form number + new header = new endorsement
        assert is_cont is False

    def test_multi_page_endorsement_via_form_number(self, tracker):
        """Test tracking a 4-page endorsement via form numbers."""
        form_number = "CA T3 53 02 15"

        # Page 5 - Start of endorsement
        page5_signals = PageSignals(
            page_number=5,
            top_lines=["THIS ENDORSEMENT CHANGES THE POLICY"],
            all_lines=["BUSINESS AUTO EXTENSION ENDORSEMENT"],
            text_density=0.8,
            has_tables=False,
            page_hash="hash5",
            has_endorsement_header=True,
            form_number=form_number,
            section_labels=["A", "B", "C"],
        )
        tracker.start_endorsement(page5_signals)

        # Pages 6, 7, 8 - Continuations
        for page_num in [6, 7, 8]:
            signals = PageSignals(
                page_number=page_num,
                top_lines=[f"Section content for page {page_num}"],
                all_lines=[f"Content for page {page_num}"],
                text_density=0.8,
                has_tables=False,
                page_hash=f"hash{page_num}",
                has_endorsement_header=False,
                form_number=form_number,  # Same form number
            )
            is_cont, ctx, conf, reason = tracker.check_continuation(signals)
            assert is_cont is True
            assert ctx.endorsement_id == form_number

        # Verify all pages are tracked
        summary = tracker.get_endorsement_summary()
        assert len(summary["endorsements"]) == 1
        assert summary["endorsements"][0]["pages"] == [5, 6, 7, 8]
        assert summary["endorsements"][0]["page_count"] == 4


class TestCertificateShouldProcessFlag:
    """Tests for certificate should_process = False behavior."""

    @pytest.fixture
    def classifier(self):
        return PageClassifier.get_instance()

    def test_certificate_should_process_false_in_batch(self, classifier):
        """Test that certificate pages have should_process=False in batch classification."""
        signals_list = [
            PageSignals(
                page_number=1,
                top_lines=["CERTIFICATE OF LIABILITY INSURANCE"],
                all_lines=[
                    "CERTIFICATE OF LIABILITY INSURANCE",
                    "THIS CERTIFICATE IS ISSUED AS A MATTER OF INFORMATION",
                ],
                text_density=0.8,
                has_tables=True,
                page_hash="hash1",
            ),
            PageSignals(
                page_number=2,
                top_lines=["THIS ENDORSEMENT CHANGES THE POLICY"],
                all_lines=["THIS ENDORSEMENT CHANGES THE POLICY", "BUSINESS AUTO"],
                text_density=0.8,
                has_tables=False,
                page_hash="hash2",
                has_endorsement_header=True,
            ),
        ]

        classifications = classifier.classify_batch(
            signals_list, doc_type=DocumentType.POLICY_BUNDLE
        )

        # Certificate should have should_process=False
        assert classifications[0].page_type == PageType.CERTIFICATE_OF_INSURANCE
        assert classifications[0].should_process is False

        # Endorsement should have should_process=True
        assert classifications[1].page_type == PageType.ENDORSEMENT
        assert classifications[1].should_process is True
