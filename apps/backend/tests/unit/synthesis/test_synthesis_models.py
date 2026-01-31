"""Unit tests for synthesis data models."""

import pytest
from pydantic import ValidationError


class TestEffectiveCoverageModel:
    """Test suite for EffectiveCoverage schema."""

    def test_effective_coverage_valid(self):
        """Test creating a valid EffectiveCoverage."""
        from app.schemas.product.synthesis_models import EffectiveCoverage

        coverage = EffectiveCoverage(
            coverage_name="Business Auto Liability",
            effective_terms={
                "hired_auto": "Covered",
                "non_owned_auto": "Covered",
                "supplementary_payments": "Expanded",
            },
            sources=["Business Auto Coverage Form", "Business Auto Extension Endorsement"],
            confidence=0.92,
        )
        assert coverage.coverage_name == "Business Auto Liability"
        assert coverage.effective_terms["hired_auto"] == "Covered"
        assert len(coverage.sources) == 2

    def test_effective_coverage_requires_name(self):
        """Test that coverage_name is required."""
        from app.schemas.product.synthesis_models import EffectiveCoverage

        with pytest.raises(ValidationError):
            EffectiveCoverage(
                effective_terms={"hired_auto": "Covered"},
                sources=[],
            )


class TestEffectiveExclusionModel:
    """Test suite for EffectiveExclusion schema."""

    def test_effective_exclusion_valid(self):
        """Test creating a valid EffectiveExclusion."""
        from app.schemas.product.synthesis_models import EffectiveExclusion

        exclusion = EffectiveExclusion(
            exclusion_name="Pollution Exclusion",
            effective_state="Partially Excluded",
            carve_backs=["Sudden and accidental releases"],
            sources=["CG 00 01", "CG 24 17"],
            confidence=0.88,
        )
        assert exclusion.exclusion_name == "Pollution Exclusion"
        assert exclusion.effective_state == "Partially Excluded"
        assert len(exclusion.carve_backs) == 1


class TestSynthesisResultModel:
    """Test suite for SynthesisResult schema."""

    def test_synthesis_result_valid(self):
        """Test creating a valid SynthesisResult."""
        from app.schemas.product.synthesis_models import (
            EffectiveCoverage,
            EffectiveExclusion,
            SynthesisResult,
        )

        result = SynthesisResult(
            effective_coverages=[
                EffectiveCoverage(
                    coverage_name="Auto Liability",
                    effective_terms={"hired_auto": "Covered"},
                    sources=["CA 00 01"],
                    confidence=0.9,
                )
            ],
            effective_exclusions=[
                EffectiveExclusion(
                    exclusion_name="Racing",
                    effective_state="Excluded",
                    sources=["CA 00 01"],
                    confidence=0.95,
                )
            ],
            overall_confidence=0.88,
            synthesis_method="endorsement_only",
        )
        assert len(result.effective_coverages) == 1
        assert len(result.effective_exclusions) == 1
        assert result.synthesis_method == "endorsement_only"
