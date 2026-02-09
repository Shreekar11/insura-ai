"""Integration tests for synthesis in extraction pipeline."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


class TestPipelineIntegration:
    """Test suite for synthesis integration with extraction pipeline."""

    @pytest.fixture
    def mock_extraction_response(self):
        """Mock LLM extraction response with endorsements."""
        return {
            "endorsements": [
                {
                    "endorsement_name": "BUSINESS AUTO EXTENSION",
                    "endorsement_type": "Add",
                    "impacted_coverage": "BUSINESS AUTO COVERAGE FORM",
                }
            ],
            "entities": [],
            "confidence": 0.9,
        }

    def test_document_extraction_result_includes_synthesis(self, mock_extraction_response):
        """Test that DocumentExtractionResult includes synthesis data."""
        from app.services.extracted.services.extraction.section.section_extraction_orchestrator import (
            DocumentExtractionResult,
            SectionExtractionResult,
        )
        from app.services.processed.services.chunking.hybrid_models import SectionType

        result = DocumentExtractionResult(
            document_id=uuid4(),
            section_results=[
                SectionExtractionResult(
                    section_type=SectionType.ENDORSEMENTS,
                    extracted_data=mock_extraction_response,
                    confidence=0.9,
                )
            ],
        )

        # Convert to dict and run synthesis
        result_dict = result.to_dict()

        from app.services.extracted.services.synthesis import SynthesisOrchestrator
        orchestrator = SynthesisOrchestrator()
        augmented = orchestrator.augment_extraction_result(result_dict)

        assert "effective_coverages" in augmented
        assert "effective_exclusions" in augmented
        assert "synthesis_metadata" in augmented

    def test_synthesis_runs_on_endorsement_extraction(self):
        """Test that synthesis produces output from endorsement data."""
        from app.services.extracted.services.synthesis import SynthesisOrchestrator

        extraction_result = {
            "document_id": str(uuid4()),
            "section_results": [
                {
                    "section_type": "endorsements",
                    "extracted_data": {
                        "endorsements": [
                            {
                                "endorsement_name": "Hired Auto Coverage",
                                "endorsement_type": "Add",
                                "impacted_coverage": "Business Auto Liability",
                                "materiality": "High",
                            }
                        ]
                    },
                    "confidence": 0.85,
                }
            ],
        }

        orchestrator = SynthesisOrchestrator()
        result = orchestrator.synthesize(extraction_result)

        assert len(result.get("effective_coverages", [])) > 0
        assert result.get("synthesis_method") == "endorsement_only"
