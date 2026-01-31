"""Unit tests for CoverageSynthesizer service."""

import pytest
from unittest.mock import AsyncMock, MagicMock


class TestCoverageSynthesizer:
    """Test suite for CoverageSynthesizer."""

    @pytest.fixture
    def sample_endorsement_modifications(self):
        """Sample endorsement modifications from extraction."""
        return {
            "endorsements": [
                {
                    "endorsement_number": "CA T4 52 02 16",
                    "endorsement_name": "Short Term Hired Auto",
                    "modifications": [
                        {
                            "impacted_coverage": "Covered Autos Liability Coverage",
                            "coverage_effect": "Expand",
                            "effect_category": "expands_coverage",
                            "scope_modification": "Extends coverage to non-owned autos used in business for up to 30 days",
                            "condition_modification": "Coverage limited to 30 days or less",
                            "verbatim_language": "Coverage is extended to apply to those autos...",
                        }
                    ],
                },
                {
                    "endorsement_number": "IL 00 21",
                    "endorsement_name": "Blanket Additional Insured",
                    "modifications": [
                        {
                            "impacted_coverage": "Business Auto Liability",
                            "coverage_effect": "Add",
                            "effect_category": "adds_coverage",
                            "scope_modification": "Adds additional insureds as required by contract",
                        }
                    ],
                },
            ],
            "all_modifications": [],
        }

    @pytest.fixture
    def sample_endorsement_data(self):
        """Sample endorsements from basic extraction (not projection)."""
        return {
            "endorsements": [
                {
                    "endorsement_name": "BUSINESS AUTO EXTENSION ENDORSEMENT",
                    "endorsement_type": "Add",
                    "impacted_coverage": "BUSINESS AUTO COVERAGE FORM",
                    "materiality": "Medium",
                },
                {
                    "endorsement_name": "BLANKET ADDITIONAL INSURED",
                    "endorsement_type": "Add",
                    "impacted_coverage": "BUSINESS AUTO COVERAGE FORM",
                    "materiality": "High",
                },
            ]
        }

    def test_synthesize_from_endorsement_modifications(self, sample_endorsement_modifications):
        """Test synthesizing coverages from endorsement projection modifications."""
        from app.services.extracted.services.synthesis.coverage_synthesizer import (
            CoverageSynthesizer,
        )

        synthesizer = CoverageSynthesizer()
        result = synthesizer.synthesize_coverages(
            endorsement_modifications=sample_endorsement_modifications,
            base_coverages=None,
        )

        assert len(result.effective_coverages) >= 1
        assert result.synthesis_method == "endorsement_only"

        # Check that "Covered Autos Liability Coverage" was synthesized
        coverage_names = [c.coverage_name for c in result.effective_coverages]
        assert "Covered Autos Liability Coverage" in coverage_names or "Business Auto Liability" in coverage_names

    def test_synthesize_groups_by_coverage(self, sample_endorsement_modifications):
        """Test that modifications affecting same coverage are grouped."""
        from app.services.extracted.services.synthesis.coverage_synthesizer import (
            CoverageSynthesizer,
        )

        synthesizer = CoverageSynthesizer()
        result = synthesizer.synthesize_coverages(
            endorsement_modifications=sample_endorsement_modifications,
            base_coverages=None,
        )

        # Each unique coverage should have a single entry
        coverage_names = [c.coverage_name for c in result.effective_coverages]
        assert len(coverage_names) == len(set(coverage_names)), "Duplicate coverage names found"

    def test_synthesize_tracks_sources(self, sample_endorsement_modifications):
        """Test that source endorsements are tracked."""
        from app.services.extracted.services.synthesis.coverage_synthesizer import (
            CoverageSynthesizer,
        )

        synthesizer = CoverageSynthesizer()
        result = synthesizer.synthesize_coverages(
            endorsement_modifications=sample_endorsement_modifications,
            base_coverages=None,
        )

        # At least one coverage should have sources
        coverages_with_sources = [c for c in result.effective_coverages if c.sources]
        assert len(coverages_with_sources) > 0

    def test_synthesize_from_basic_endorsements(self, sample_endorsement_data):
        """Test synthesizing from basic endorsement extraction (non-projection)."""
        from app.services.extracted.services.synthesis.coverage_synthesizer import (
            CoverageSynthesizer,
        )

        synthesizer = CoverageSynthesizer()
        result = synthesizer.synthesize_coverages(
            endorsement_modifications=None,
            endorsement_data=sample_endorsement_data,
            base_coverages=None,
        )

        assert len(result.effective_coverages) >= 1
        # Should still produce coverage entries from basic endorsement data

    def test_synthesize_empty_input(self):
        """Test synthesizing with no input returns empty result."""
        from app.services.extracted.services.synthesis.coverage_synthesizer import (
            CoverageSynthesizer,
        )

        synthesizer = CoverageSynthesizer()
        result = synthesizer.synthesize_coverages(
            endorsement_modifications=None,
            base_coverages=None,
        )

        assert len(result.effective_coverages) == 0
        assert result.overall_confidence == 0.0

    def test_confidence_calculation(self, sample_endorsement_modifications):
        """Test that overall confidence is calculated."""
        from app.services.extracted.services.synthesis.coverage_synthesizer import (
            CoverageSynthesizer,
        )

        synthesizer = CoverageSynthesizer()
        result = synthesizer.synthesize_coverages(
            endorsement_modifications=sample_endorsement_modifications,
            base_coverages=None,
        )

        assert result.overall_confidence > 0.0
        assert result.overall_confidence <= 1.0
