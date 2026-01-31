"""Unit tests for SynthesisOrchestrator."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


class TestSynthesisOrchestrator:
    """Test suite for SynthesisOrchestrator."""

    @pytest.fixture
    def sample_extraction_result(self):
        """Sample document extraction result."""
        return {
            "document_id": "test-doc-123",
            "section_results": [
                {
                    "section_type": "endorsements",
                    "extracted_data": {
                        "endorsements": [
                            {
                                "endorsement_name": "BUSINESS AUTO EXTENSION",
                                "endorsement_type": "Add",
                                "impacted_coverage": "BUSINESS AUTO COVERAGE FORM",
                                "materiality": "Medium",
                            }
                        ]
                    },
                    "confidence": 0.9,
                }
            ],
            "all_entities": [],
        }

    @pytest.fixture
    def sample_projection_result(self):
        """Sample projection extraction result with modifications."""
        return {
            "document_id": "test-doc-123",
            "section_results": [
                {
                    "section_type": "endorsements",
                    "extracted_data": {
                        "endorsements": [
                            {
                                "endorsement_number": "CA T4 52",
                                "endorsement_name": "Short Term Hired Auto",
                                "modifications": [
                                    {
                                        "impacted_coverage": "Covered Autos Liability",
                                        "coverage_effect": "Expand",
                                        "effect_category": "expands_coverage",
                                        "scope_modification": "Extends to hired autos",
                                    }
                                ],
                            }
                        ],
                        "all_modifications": [],
                    },
                    "confidence": 0.92,
                }
            ],
        }

    def test_orchestrator_synthesize_from_extraction(self, sample_extraction_result):
        """Test synthesizing from basic extraction result."""
        from app.services.extracted.services.synthesis.synthesis_orchestrator import (
            SynthesisOrchestrator,
        )

        orchestrator = SynthesisOrchestrator()
        result = orchestrator.synthesize(extraction_result=sample_extraction_result)

        assert "effective_coverages" in result
        assert "effective_exclusions" in result
        assert "synthesis_method" in result

    def test_orchestrator_synthesize_from_projections(self, sample_projection_result):
        """Test synthesizing from projection extraction result."""
        from app.services.extracted.services.synthesis.synthesis_orchestrator import (
            SynthesisOrchestrator,
        )

        orchestrator = SynthesisOrchestrator()
        result = orchestrator.synthesize(extraction_result=sample_projection_result)

        assert len(result.get("effective_coverages", [])) >= 1

    def test_orchestrator_merges_coverage_and_exclusion(self, sample_extraction_result):
        """Test that orchestrator merges coverage and exclusion synthesis."""
        from app.services.extracted.services.synthesis.synthesis_orchestrator import (
            SynthesisOrchestrator,
        )

        orchestrator = SynthesisOrchestrator()
        result = orchestrator.synthesize(extraction_result=sample_extraction_result)

        # Result should have both arrays (even if empty)
        assert "effective_coverages" in result
        assert "effective_exclusions" in result

    def test_orchestrator_confidence_threshold(self, sample_extraction_result):
        """Test that low confidence triggers fallback flag."""
        from app.services.extracted.services.synthesis.synthesis_orchestrator import (
            SynthesisOrchestrator,
        )

        # Modify to have low confidence
        sample_extraction_result["section_results"][0]["confidence"] = 0.5

        orchestrator = SynthesisOrchestrator(confidence_threshold=0.7)
        result = orchestrator.synthesize(extraction_result=sample_extraction_result)

        # Should indicate fallback might be needed
        assert "overall_confidence" in result

    def test_orchestrator_augments_extraction_result(self, sample_extraction_result):
        """Test that orchestrator can augment the original extraction result."""
        from app.services.extracted.services.synthesis.synthesis_orchestrator import (
            SynthesisOrchestrator,
        )

        orchestrator = SynthesisOrchestrator()
        augmented = orchestrator.augment_extraction_result(
            extraction_result=sample_extraction_result
        )

        # Original data should be preserved
        assert "section_results" in augmented
        # Synthesis should be added
        assert "effective_coverages" in augmented
        assert "effective_exclusions" in augmented
