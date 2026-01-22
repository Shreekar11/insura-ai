import pytest
from app.models.page_analysis_models import PageSignals, PageType, SemanticRole, ExclusionEffect, CoverageEffect
from app.services.processed.services.analysis.page_classifier import PageClassifier

def test_span_semantic_intent_detection():
    """Test that individual spans can detect semantic intent correctly."""
    classifier = PageClassifier()
    
    # Page content with an EXCLUSIONS section followed by an ENDORSEMENT section
    # The endorsement section contains keywords that should trigger 'narrows_exclusion' and 'removes_exclusion'
    lines = [
        "## EXCLUSIONS",
        "The following are excluded from coverage:",
        "1. Nuclear hazards",
        "2. War and insurrection",
        "",
        "## AMENDATORY ENDORSEMENT",
        "THIS ENDORSEMENT CHANGES THE POLICY. PLEASE READ IT CAREFULLY.",
        "The exclusion for Nuclear hazards is hereby removed from this policy.",
        "The exclusion for War is narrowed to only apply in non-NATO countries.",
    ]
    
    signals = PageSignals(
        page_number=5,
        top_lines=lines[:1],
        all_lines=lines,
        text_density=0.7,
        has_tables=False,
        max_font_size=18.0,
        page_hash="mixed_page_semantic"
    )
    
    classification = classifier.classify(signals)
    
    # Should have detected two spans
    assert len(classification.sections) == 2
    
    # Span 1: Exclusions
    excl_span = classification.sections[0]
    assert excl_span.section_type == PageType.EXCLUSIONS
    assert excl_span.semantic_role == SemanticRole.UNKNOWN
    assert not excl_span.exclusion_effects
    
    # Span 2: Endorsement
    end_span = classification.sections[1]
    assert end_span.section_type == PageType.ENDORSEMENT
    assert end_span.semantic_role in {SemanticRole.EXCLUSION_MODIFIER, SemanticRole.BOTH}
    assert ExclusionEffect.REMOVES_EXCLUSION in end_span.exclusion_effects
    assert ExclusionEffect.NARROWS_EXCLUSION in end_span.exclusion_effects

if __name__ == "__main__":
    pytest.main([__file__])
