"""Unit tests for BaseCoverageInferenceService."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestBaseCoverageInferenceService:
    """Test suite for BaseCoverageInferenceService."""

    @pytest.fixture
    def mock_llm_response(self):
        """Mock LLM response for base coverage inference."""
        return """{
            "inferred_coverages": [
                {
                    "coverage_name": "Covered Autos Liability",
                    "typical_terms": {
                        "bodily_injury": "Covered",
                        "property_damage": "Covered",
                        "hired_auto": "Not Covered (standard)",
                        "non_owned_auto": "Not Covered (standard)"
                    },
                    "form_reference": "CA 00 01"
                }
            ],
            "confidence": 0.85,
            "reasoning": "Business Auto Coverage Form CA 00 01 provides standard auto liability coverage"
        }"""

    @pytest.fixture
    def inference_service(self, mock_llm_response):
        """Create inference service with mocked LLM client."""
        with patch('app.services.extracted.services.synthesis.base_coverage_inference.create_llm_client_from_settings') as MockFactory:
            mock_client = AsyncMock()
            mock_client.generate_content = AsyncMock(return_value=mock_llm_response)
            MockFactory.return_value = mock_client

            from app.services.extracted.services.synthesis.base_coverage_inference import (
                BaseCoverageInferenceService,
            )

            service = BaseCoverageInferenceService(
                provider="gemini",
                gemini_api_key="test-key",
                gemini_model="gemini-2.0-flash",
            )
            service.client = mock_client
            return service

    @pytest.mark.asyncio
    async def test_infer_base_coverages(self, inference_service):
        """Test inferring base coverages from form references."""
        result = await inference_service.infer_base_coverages(
            form_references=["CA 00 01", "Business Auto Coverage Form"],
        )

        assert "inferred_coverages" in result
        assert len(result["inferred_coverages"]) > 0

    @pytest.mark.asyncio
    async def test_infer_returns_confidence(self, inference_service):
        """Test that inference returns confidence score."""
        result = await inference_service.infer_base_coverages(
            form_references=["CA 00 01"],
        )

        assert "confidence" in result
        assert result["confidence"] > 0

    @pytest.mark.asyncio
    async def test_infer_empty_references(self, inference_service):
        """Test inference with empty references returns empty result."""
        result = await inference_service.infer_base_coverages(
            form_references=[],
        )

        assert result.get("inferred_coverages", []) == []
