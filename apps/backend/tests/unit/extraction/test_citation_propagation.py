import pytest
from app.services.extracted.services.extraction.section.section_extraction_orchestrator import SectionExtractionOrchestrator
from app.services.extracted.services.synthesis.coverage_synthesizer import CoverageSynthesizer
from app.services.extracted.services.synthesis.exclusion_synthesizer import ExclusionSynthesizer
from app.services.processed.services.chunking.hybrid_models import SectionType

from unittest.mock import MagicMock

@pytest.fixture
def orchestrator():
    # Mock orchestrator for testing internal methods
    mock_session = MagicMock()
    return SectionExtractionOrchestrator(session=mock_session)

@pytest.fixture
def coverage_synthesizer():
    return CoverageSynthesizer()

@pytest.fixture
def exclusion_synthesizer():
    return ExclusionSynthesizer()

def test_inject_page_numbers_nested_modifications(orchestrator):
    extracted_data = {
        "endorsements": [
            {
                "endorsement_name": "Test Endorsement",
                "modifications": [
                    {"impacted_coverage": "Auto", "coverage_effect": "Add"},
                    {"impacted_coverage": "Liability", "verbatim_language": "Testing verbatim"}
                ]
            }
        ]
    }
    page_range = [5, 6]
    
    result = orchestrator._inject_page_numbers(extracted_data, page_range, "endorsements")
    
    # Check top-level endorsement
    assert result["endorsements"][0]["page_numbers"] == [5, 6]
    
    # Check nested modifications
    nested_mods = result["endorsements"][0]["modifications"]
    assert nested_mods[0]["page_numbers"] == [5, 6]
    assert nested_mods[1]["page_numbers"] == [5, 6]
    
    # Check verbatim sync to source_text
    assert nested_mods[1]["source_text"] == "Testing verbatim"

def test_coverage_synthesizer_propagation(coverage_synthesizer):
    endorsement_modifications = {
        "endorsements": [
            {
                "endorsement_number": "CA 20 48",
                "modifications": [
                    {
                        "impacted_coverage": "Auto",
                        "coverage_effect": "Add",
                        "effect_category": "adds_coverage",
                        "page_numbers": [10, 11],
                        "source_text": "Verbatim coverage text"
                    }
                ]
            }
        ]
    }
    
    result = coverage_synthesizer.synthesize_coverages(
        endorsement_modifications=endorsement_modifications
    )
    
    assert len(result.effective_coverages) > 0
    cov = result.effective_coverages[0]
    assert cov.page_numbers == [10, 11]
    assert cov.source_text == "Verbatim coverage text"

def test_exclusion_synthesizer_propagation(exclusion_synthesizer):
    exclusion_modifications = {
        "endorsements": [
            {
                "endorsement_number": "EX 100",
                "modifications": [
                    {
                        "impacted_exclusion": "Nuclear",
                        "exclusion_effect": "Add",
                        "effect_category": "introduces_exclusion",
                        "page_numbers": [12],
                        "source_text": "Nuclear exclusion text"
                    }
                ]
            }
        ]
    }
    
    result = exclusion_synthesizer.synthesize_exclusions(
        exclusion_modifications=exclusion_modifications
    )
    
    assert len(result.effective_exclusions) > 0
    excl = result.effective_exclusions[0]
    assert excl.page_numbers == [12]
    assert excl.source_text == "Nuclear exclusion text"
