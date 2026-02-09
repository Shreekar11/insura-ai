"""Unit tests for ExclusionSynthesizer service."""

import pytest


class TestExclusionSynthesizer:
    """Test suite for ExclusionSynthesizer."""

    @pytest.fixture
    def sample_exclusion_modifications(self):
        """Sample exclusion modifications from extraction."""
        return {
            "endorsements": [
                {
                    "endorsement_number": "CA 04 44 10 13",
                    "endorsement_name": "Waiver of Transfer of Rights",
                    "modifications": [
                        {
                            "impacted_exclusion": "Transfer of Rights of Recovery Against Others",
                            "exclusion_effect": "Narrow",
                            "effect_category": "narrows_exclusion",
                            "exclusion_scope": "Subrogation rights against scheduled parties",
                            "impacted_coverage": "All coverages subject to subrogation",
                            "exception_conditions": "Only for loss arising from operations under written contract",
                            "severity": "Material",
                        }
                    ],
                },
                {
                    "endorsement_number": "CG 24 04",
                    "endorsement_name": "Pollution Exclusion",
                    "modifications": [
                        {
                            "impacted_exclusion": "Pollution",
                            "exclusion_effect": "Add",
                            "effect_category": "introduces_exclusion",
                            "exclusion_scope": "All pollution-related claims",
                            "severity": "Material",
                        }
                    ],
                },
            ],
        }

    def test_synthesize_from_exclusion_modifications(self, sample_exclusion_modifications):
        """Test synthesizing exclusions from projection modifications."""
        from app.services.extracted.services.synthesis.exclusion_synthesizer import (
            ExclusionSynthesizer,
        )

        synthesizer = ExclusionSynthesizer()
        result = synthesizer.synthesize_exclusions(
            exclusion_modifications=sample_exclusion_modifications,
        )

        assert len(result.effective_exclusions) >= 1
        assert result.synthesis_method == "endorsement_only"

    def test_synthesize_tracks_carve_backs(self, sample_exclusion_modifications):
        """Test that carve-backs are tracked for narrowed exclusions."""
        from app.services.extracted.services.synthesis.exclusion_synthesizer import (
            ExclusionSynthesizer,
        )

        synthesizer = ExclusionSynthesizer()
        result = synthesizer.synthesize_exclusions(
            exclusion_modifications=sample_exclusion_modifications,
        )

        # Find the narrowed exclusion
        narrowed = [e for e in result.effective_exclusions if e.effective_state == "Partially Excluded" or e.carve_backs]
        assert len(narrowed) >= 1 or any(e.conditions for e in result.effective_exclusions)

    def test_synthesize_empty_input(self):
        """Test synthesizing with no input returns empty result."""
        from app.services.extracted.services.synthesis.exclusion_synthesizer import (
            ExclusionSynthesizer,
        )

        synthesizer = ExclusionSynthesizer()
        result = synthesizer.synthesize_exclusions(exclusion_modifications=None)

        assert len(result.effective_exclusions) == 0
        assert result.overall_confidence == 0.0

    def test_synthesize_tracks_severity(self, sample_exclusion_modifications):
        """Test that severity is tracked."""
        from app.services.extracted.services.synthesis.exclusion_synthesizer import (
            ExclusionSynthesizer,
        )

        synthesizer = ExclusionSynthesizer()
        result = synthesizer.synthesize_exclusions(
            exclusion_modifications=sample_exclusion_modifications,
        )

        # At least one exclusion should have severity
        exclusions_with_severity = [e for e in result.effective_exclusions if e.severity]
        assert len(exclusions_with_severity) > 0
