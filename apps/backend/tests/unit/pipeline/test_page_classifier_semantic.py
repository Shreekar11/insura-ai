"""Unit tests for PageClassifier semantic intent detection.

Focuses on exclusion carve-backs and priority rules.
"""

import pytest
from app.services.processed.services.analysis.page_classifier import PageClassifier
from app.models.page_analysis_models import PageSignals, PageType, SemanticRole, ExclusionEffect, CoverageEffect, DocumentType


class TestPageClassifierSemantic:
    """Test semantic intent detection with new exclusion rules."""
    
    @pytest.fixture
    def classifier(self):
        return PageClassifier(confidence_threshold=0.7)
    
    def _create_signals(self, text: str, page_number: int = 7) -> PageSignals:
        lines = text.split("\n")
        return PageSignals(
            page_number=page_number,
            top_lines=lines[:5],
            all_lines=lines,
            text_density=0.8,
            has_tables=False,
            max_font_size=12.0,
            page_hash="hash" + str(page_number)
        )

    def test_exclusion_carve_back_narrows(self, classifier):
        """Test detection of 'exclusion does not apply' carve-back."""
        text = """
        THIS ENDORSEMENT CHANGES THE POLICY. PLEASE READ IT CAREFULLY.
        The following is added to Paragraph B.3., Exclusions,
        of SECTION III - PHYSICAL DAMAGE COVERAGE:
        
        Exclusion 3.a. does not apply to "loss" to one or more airbags...
        """
        signals = self._create_signals(text)
        result = classifier.classify(signals, doc_type=DocumentType.ENDORSEMENT)
        
        assert result.page_type == PageType.ENDORSEMENT
        assert result.semantic_role == SemanticRole.EXCLUSION_MODIFIER
        assert ExclusionEffect.NARROWS_EXCLUSION in result.exclusion_effects

    def test_conditional_exclusion_override(self, classifier):
        """Test detection of conditional exclusion override."""
        text = """
        THIS ENDORSEMENT CHANGES THE POLICY.
        This exclusion does not apply to bodily injury but only if
        the insured has obtained prior written consent...
        """
        signals = self._create_signals(text)
        result = classifier.classify(signals, doc_type=DocumentType.ENDORSEMENT)
        
        assert result.semantic_role == SemanticRole.EXCLUSION_MODIFIER
        assert ExclusionEffect.NARROWS_EXCLUSION in result.exclusion_effects

    def test_exclusion_replacement_removes(self, classifier):
        """Test detection of exclusion replacement."""
        text = """
        POLICY CHANGE ENDORSEMENT
        The following replaces Paragraph 2. Exclusions:
        All previous exclusions are hereby deleted and replaced with...
        """
        signals = self._create_signals(text)
        result = classifier.classify(signals, doc_type=DocumentType.ENDORSEMENT)
        
        assert ExclusionEffect.REMOVES_EXCLUSION in result.exclusion_effects
        # Should also be EXCLUSION_MODIFIER or BOTH if it also adds something
        assert result.semantic_role in [SemanticRole.EXCLUSION_MODIFIER, SemanticRole.BOTH]

    def test_structural_exclusion_priority(self, classifier):
        """Test that structural exclusion references boost confidence and override role."""
        text = """
        THIS ENDORSEMENT CHANGES THE POLICY.
        SECTION III - PHYSICAL DAMAGE COVERAGE
        Paragraph B.3., Exclusions
        We will pay for damage caused by...
        """
        signals = self._create_signals(text)
        result = classifier.classify(signals, doc_type=DocumentType.ENDORSEMENT)
        
        # Even with "We will pay", structural exclusion reference should trigger EXCLUSION_MODIFIER or BOTH
        assert result.semantic_role in [SemanticRole.EXCLUSION_MODIFIER, SemanticRole.BOTH]

    def test_mixed_signals_priority(self, classifier):
        """Rule 1 test: Exclusion carve-back overrides coverage roll."""
        text = """
        THIS ENDORSEMENT CHANGES THE POLICY.
        This endorsement broadens coverage.
        However, Exclusion 4.b. does not apply to certain losses.
        """
        signals = self._create_signals(text)
        result = classifier.classify(signals, doc_type=DocumentType.ENDORSEMENT)
        
        # Both additions and carve-backs are present
        assert CoverageEffect.EXPANDS_COVERAGE in result.coverage_effects
        assert ExclusionEffect.NARROWS_EXCLUSION in result.exclusion_effects
        
        # Rule 1 says exclusion carve-back is a very specific intent we want to capture
        assert result.semantic_role == SemanticRole.EXCLUSION_MODIFIER
